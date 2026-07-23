#!/bin/bash
cd /home/kali/ARL-new
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 5003 --reload
