# test_pipeline.py — run this on Mac B to verify MediaPipe works
import cv2
from config import MAC_B_CAM_INDEX
from pipeline import _USE_TASKS, fuse_frames

print(f"MediaPipe backend: {'Tasks API' if _USE_TASKS else 'legacy solutions'}")
print("First run may download models into ./models/ (Tasks API only).")
print("Press Q to quit")

cap = cv2.VideoCapture(MAC_B_CAM_INDEX)
if not cap.isOpened():
    print("Cannot open webcam.")
    print()
    print("macOS usually blocks this until Camera access is granted:")
    print("  System Settings → Privacy & Security → Camera")
    print("  Enable the app you run Python from (Terminal, iTerm, or Cursor).")
    print("  Quit that app fully, reopen it, then run this script again.")
    print()
    print(f"If multiple cameras exist, try MAC_B_CAM_INDEX = 1 in config.py (now {MAC_B_CAM_INDEX}).")
    raise SystemExit(1)

while True:
    ok, frame = cap.read()
    if not ok:
        print("Lost webcam mid-stream.")
        break

    fake_registry = {"mac_b_builtin": frame}
    output = fuse_frames(fake_registry)

    cv2.imshow("WallSight pipeline test", output)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
