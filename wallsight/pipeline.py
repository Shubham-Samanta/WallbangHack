# pipeline.py
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional

import cv2
import mediapipe as mp
import numpy as np

from config import TARGET_H, TARGET_W

_USE_TASKS = not hasattr(mp, "solutions")

# Temporal mask blend — reduces body fill dropping between frames
_prev_mask: Optional[np.ndarray] = None
MASK_SMOOTH = 0.72
_VISIBILITY_MIN = 0.55

_video_ts = 0
pose_model = None
seg_model = None
_POSE_CONNECTIONS = None


def _init_legacy():
    global pose_model, seg_model, _POSE_CONNECTIONS, _mp_drawing
    _mp_pose = mp.solutions.pose
    _mp_seg = mp.solutions.selfie_segmentation
    _mp_drawing = mp.solutions.drawing_utils
    pose_model = _mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,
        smooth_landmarks=True,
        smooth_segmentation=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.4,
    )
    seg_model = _mp_seg.SelfieSegmentation(model_selection=1)
    _POSE_CONNECTIONS = _mp_pose.POSE_CONNECTIONS


if _USE_TASKS:
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.vision import drawing_utils as _mp_drawing
    from mediapipe.tasks.python.vision.pose_landmarker import PoseLandmarksConnections

    _MODEL_DIR = Path(__file__).parent / "models"
    _POSE_MODEL = _MODEL_DIR / "pose_landmarker_lite.task"
    _SEG_MODEL = _MODEL_DIR / "selfie_segmenter.tflite"
    _MODEL_URLS = {
        _POSE_MODEL: (
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
        ),
        _SEG_MODEL: (
            "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
            "selfie_segmenter/float16/latest/selfie_segmenter.tflite"
        ),
    }

    def _ensure_model(path: Path, url: str) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[pipeline] Downloading {path.name}...")
        urllib.request.urlretrieve(url, path)

    def _init_tasks():
        global pose_model, seg_model, _POSE_CONNECTIONS
        for _path, _url in _MODEL_URLS.items():
            _ensure_model(_path, _url)
        pose_model = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(model_asset_path=str(_POSE_MODEL)),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.4,
                output_segmentation_masks=False,
            )
        )
        seg_model = vision.ImageSegmenter.create_from_options(
            vision.ImageSegmenterOptions(
                base_options=mp_tasks.BaseOptions(model_asset_path=str(_SEG_MODEL)),
                running_mode=vision.RunningMode.IMAGE,
                output_confidence_masks=True,
                output_category_mask=False,
            )
        )
        _POSE_CONNECTIONS = PoseLandmarksConnections.POSE_LANDMARKS

else:
    _init_tasks = _init_legacy  # type: ignore[assignment]


def _ensure_models():
    global pose_model
    if pose_model is None:
        _init_tasks() if _USE_TASKS else _init_legacy()


def _smooth_mask(new_mask: np.ndarray) -> np.ndarray:
    global _prev_mask
    if _prev_mask is None:
        _prev_mask = new_mask.copy()
        return new_mask
    smoothed = cv2.addWeighted(_prev_mask, MASK_SMOOTH, new_mask, 1 - MASK_SMOOTH, 0)
    _prev_mask = smoothed
    return smoothed


def _landmark_score(lm) -> float:
    if lm.visibility is not None:
        return lm.visibility
    if getattr(lm, "presence", None) is not None:
        return lm.presence
    return 1.0


def _mask_from_tasks_image(mask_image) -> Optional[np.ndarray]:
    if mask_image is None:
        return None
    mask = np.squeeze(mask_image.numpy_view()).astype(np.float32)
    return mask


def process_frame(frame: np.ndarray):
    """
    Input:  BGR numpy frame (any size)
    Output: (pose_result, seg_result) — same shape for legacy and Tasks API
    """
    _ensure_models()
    if _USE_TASKS:
        global _video_ts
        _video_ts += 33
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        pose_out = pose_model.detect_for_video(mp_image, _video_ts)
        seg_out = seg_model.segment(mp_image)

        landmarks = (
            pose_out.pose_landmarks[0] if pose_out.pose_landmarks else None
        )
        mask = None
        if seg_out.confidence_masks:
            mask = _mask_from_tasks_image(seg_out.confidence_masks[0])

        pose_result = SimpleNamespace(pose_landmarks=landmarks)
        seg_result = SimpleNamespace(segmentation_mask=mask)
        return pose_result, seg_result

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    pose_result = pose_model.process(rgb)
    seg_result = seg_model.process(rgb)
    rgb.flags.writeable = True
    return pose_result, seg_result


def fuse_frames(frames: Dict[str, np.ndarray]) -> np.ndarray:
    """
    Input:  dict of {camera_id: BGR frame} from registry.get_all_active()
    Output: final styled BGR frame ready to JPEG-encode and stream
    """
    if not frames:
        blank = np.zeros((TARGET_H, TARGET_W, 3), dtype=np.uint8)
        cv2.putText(
            blank,
            "NO CAMERAS",
            (TARGET_W // 2 - 80, TARGET_H // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 100, 80),
            2,
        )
        return blank

    cam_ids = list(frames.keys())
    results = {}

    for cid, frame in frames.items():
        resized = cv2.resize(frame, (TARGET_W, TARGET_H))
        frames[cid] = resized
        results[cid] = process_frame(resized)

    primary_id = "mac_b_builtin" if "mac_b_builtin" in cam_ids else cam_ids[0]
    primary_frame = frames[primary_id]
    primary_pose = results[primary_id][0]
    _, primary_seg = results[primary_id]

    primary_mask = np.zeros((TARGET_H, TARGET_W), dtype=np.float32)
    if primary_seg.segmentation_mask is not None:
        primary_mask = cv2.resize(
            primary_seg.segmentation_mask, (TARGET_W, TARGET_H)
        )

    smoothed_mask = _smooth_mask(primary_mask)

    return apply_valorant_fx(primary_frame, smoothed_mask, primary_pose)


def apply_valorant_fx(
    frame: np.ndarray, mask: np.ndarray, pose_result
) -> np.ndarray:
    """Real frame + cyan edge glow, person tint, skeleton, scanlines."""
    output = frame.copy()

    mask_hard = (mask > 0.35).astype(np.float32)
    mask_u8 = (mask_hard * 255).astype(np.uint8)
    edges = cv2.Canny(mask_u8, 20, 90)
    glow = cv2.GaussianBlur(edges, (0, 0), sigmaX=5)
    g16 = glow.astype(np.int16)
    output[:, :, 0] = np.clip(output[:, :, 0].astype(np.int16) + g16, 0, 255)
    output[:, :, 1] = np.clip(output[:, :, 1].astype(np.int16) + g16, 0, 255)
    output[:, :, 2] = np.clip(output[:, :, 2].astype(np.int16) - g16 // 2, 0, 255)

    mask_soft = cv2.GaussianBlur(mask_hard, (0, 0), sigmaX=6)
    person = output.astype(np.float32)
    person[:, :, 2] *= 1 - mask_soft * 0.4
    person[:, :, 0] *= 1 + mask_soft * 0.3
    output = np.clip(person, 0, 255).astype(np.uint8)

    if pose_result and pose_result.pose_landmarks:
        raw = pose_result.pose_landmarks
        landmarks = raw.landmark if hasattr(raw, "landmark") else raw
        ih, iw = output.shape[:2]

        for conn in _POSE_CONNECTIONS:
            if hasattr(conn, "start"):
                i0, i1 = conn.start, conn.end
            else:
                i0, i1 = conn[0], conn[1]
            pt1, pt2 = landmarks[i0], landmarks[i1]
            if _landmark_score(pt1) > _VISIBILITY_MIN and _landmark_score(pt2) > _VISIBILITY_MIN:
                x1, y1 = int(pt1.x * iw), int(pt1.y * ih)
                x2, y2 = int(pt2.x * iw), int(pt2.y * ih)
                cv2.line(output, (x1, y1), (x2, y2), (0, 140, 255), 2)

        for lm in landmarks:
            if _landmark_score(lm) > _VISIBILITY_MIN:
                cx, cy = int(lm.x * iw), int(lm.y * ih)
                cv2.circle(output, (cx, cy), 5, (0, 220, 255), -1)
                cv2.circle(output, (cx, cy), 5, (0, 80, 180), 1)

    output[::4, :] = (output[::4, :].astype(np.float32) * 0.85).astype(np.uint8)

    return output
