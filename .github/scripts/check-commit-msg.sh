#!/bin/sh

TYPES="chore|deploy|docs|feat|fix|init|refactor|style|test"

subject=$(head -n 1 "$1")

case "$subject" in
  "Merge "* | "Revert "*) exit 0 ;;
esac

if printf '%s\n' "$subject" | grep -Eq "^($TYPES): .+"; then
  exit 0
fi

echo "커밋 메시지 형식이 올바르지 않습니다: $subject"
echo ""
echo "형식: <type>: <내용>"
echo "예시: feat: 카드 제목 생성 기능 추가"
echo ""
echo "허용 type: chore, deploy, docs, feat, fix, init, refactor, style, test"
exit 1
