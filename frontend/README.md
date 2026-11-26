# CardSync frontend

React + TypeScript (Vite).

```
npm ci
npm run dev      # http://localhost:5173
npm run build
```

백엔드: 레포 루트에서 `uvicorn backend.main:app --reload` (기본 http://localhost:8000). 먼저 내 PC에 PostgreSQL을 띄우고 개발용 DB를 만든 뒤(`createdb cardsync_dev` 등) 루트 `.env`의 `DATABASE_URL`에 그 주소를 넣는다. 운영 Supabase DB 주소는 로컬에서 쓰지 않는다. 구글 로그인 없이 쓰려면 `.env`에 `CARDSYNC_DEV_USER=local-dev`를 넣고 `frontend/.env.local`의 `VITE_SUPABASE_*`를 비워 둔다. 주소를 바꾸려면 `VITE_API_BASE`를 설정한다. 백엔드가 없으면 샘플 데이터(모의 응답)로 동작한다.
