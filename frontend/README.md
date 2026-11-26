# CardSync frontend

React + TypeScript (Vite).

```
npm ci
npm run dev      # http://localhost:5173
npm run build
```

백엔드: 레포 루트에서 `uvicorn backend.main:app --reload` (기본 http://localhost:8000). 주소를 바꾸려면 `VITE_API_BASE`를 설정한다. 백엔드가 없으면 샘플 데이터(모의 응답)로 동작한다.
