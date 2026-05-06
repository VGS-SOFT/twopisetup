# Pi4 — Gate Camera Sender

This Pi does one job only: capture from Camera v2 and stream H.264 over UDP to piANPR.

## Run manually
```bash
bash stream_sender.sh
```

## Install as systemd service (auto-start on boot)
```bash
sudo cp stream_sender.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable stream_sender
sudo systemctl start stream_sender
sudo systemctl status stream_sender
```
