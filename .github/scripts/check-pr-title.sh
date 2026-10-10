#!/bin/sh

TYPES="Init|Feat|Fix|Docs|Refactor|Chore|Test|Style|Deploy"

if printf '%s\n' "$1" | grep -Eq "^\[($TYPES)\] .+"; then
  exit 0
fi

echo "PR 제목 형식이 올바르지 않습니다: $1"
echo ""
echo "형식: [Type] <내용>"
echo "예시: [Feat] 카드 제목 생성 기능 추가"
echo ""
echo "허용 Type: Init, Feat, Fix, Docs, Refactor, Chore, Test, Style, Deploy"
exit 1
