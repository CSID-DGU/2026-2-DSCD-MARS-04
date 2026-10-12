from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

client = OpenAI()

response = client.responses.create(
    model="gpt-4.1-mini",
    input="연결 테스트입니다. 'API 연결 성공'이라고만 답하세요.",
)

print(response.output_text)