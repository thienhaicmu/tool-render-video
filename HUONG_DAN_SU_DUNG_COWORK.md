# Huong Dan Su Dung Cowork (Render Studio)

## Muc tieu
Tai lieu nay huong dan nhanh cach dung AI cowork (Claude Code, Codex) de:
- sua loi nhanh hon
- giam rui ro sua sai
- debug co quy trinh

## 1) Hieu he thong truoc khi nho AI

Render Studio la app local:
- Electron desktop + backend FastAPI
- Render tu YouTube hoac file local
- Whisper -> subtitle -> render FFmpeg
- Co upload/schedule TikTok

Nguyen tac quan trong:
- Logic pipeline nam o `backend/app/orchestration/render_pipeline.py`
- `routes/render.py` chi xu ly HTTP
- Neu render theo editor session ma session mat -> fail ro rang, khong duoc tu tai lai video

## 2) Cach goi lenh cowork

Backend co endpoint dev command:
- `POST /api/dev/command`

Body:
```json
{"command":"/run"}
```

Lenh chinh:
- `/run`: khoi dong backend neu chua chay
- `/test`: chay bo kiem tra QA
- `/fix`: auto-fix bao thu (neu du tin cay) hoac tra ve ke hoach sua

Lenh bo sung:
- `/error`, `/status`, `/commit`, `/features`

## 3) Cach dung /run /test /fix hieu qua

## `/run`
Dung khi:
- backend dang tat
- can bat lai sau khi sua code

Ky vong:
- tra trang thai da chay hay vua yeu cau start
- tra log source (`data/logs/dev_run.log`)

## `/test`
Dung sau moi patch.

Goi nhanh:
- `/test`
- `/test dev`

Nen chay it nhat 1 lan sau khi sua bug.

## `/fix`
Dung khi da co loi tu `/error` hoac log.

Vi du:
- `/fix`
- `/fix render ffmpeg`
- `/fix upload selector`

Luu y:
- Lenh nay uu tien an toan.
- Neu khong du du lieu, he thong se tra ke hoach sua thay vi tu sua manh tay.

## 4) Quy tac sua code an toan

Luon bat buoc:
1. Sua nho nhat co the.
2. Khong sua file khong lien quan.
3. Khong refactor rong khi chua duoc yeu cau.
4. Giu tuong thich API/status/path.
5. Khong bo fallback quan trong (VD NVENC->CPU, WS->polling).
6. Khong chay lenh pha huy khi chua duoc xac nhan.
7. Neu co gia dinh, phai ghi ro gia dinh.

## 5) Mau prompt de lam viec voi AI

## Mau 1: Sua bug nho
```text
Task: Sua loi render fail o stage transcribing_full.
Yeu cau: Minimal patch, khong sua file khong lien quan.
Xac minh: /test dev
Tra ve: Summary, files changed, verification, risk.
```

## Mau 2: Debug theo log
```text
Task: Phan tich loi moi nhat tu /error va de xuat fix nho nhat.
Input: error summary + job log.
Output: root cause, file/ham can sua, patch plan.
```

## Mau 3: Review patch
```text
Review patch nay theo tieu chi: scope creep, risk, missing validation.
Tra ket qua: pass/needs-fix + required fixes.
```

## 6) Cach debug nhanh khi render loi

1. Chay `/status` de xem app dang chay khong.
2. Chay `/error` de lay loi uu tien.
3. Mo log job:
   - `channels/<channel>/logs/<job_id>.log`
   - `data/logs/error.log`
4. Chay `/fix` de co patch hoac plan.
5. Chay `/test dev` sau khi sua.

## 7) Checklist truoc khi ket thuc task

- Da sua dung pham vi yeu cau?
- Da giu tuong thich he thong cu?
- Da test sau khi sua?
- Da ghi ro rui ro con lai?

Neu 4 cau tren deu "co", task cowork dat chat luong.
