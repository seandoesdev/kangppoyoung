-- 마이그레이션 V5 의 백필은 MySQL UUID()(=v1)를 사용했다. 기존 비-v4 session_id 를 UUIDv4 로 재생성한다.
-- (신규 행은 앱에서 UUID.randomUUID()=v4 를 부여하므로, 빈 DB 로 시작한 환경에는 비-v4 가 존재하지 않아 0행 처리.)
-- v4 형식: 8-4-4-4-12, 15번째 문자(version)='4', 20번째 문자(variant)∈{8,9,a,b}. RANDOM_BYTES/RAND() 는 행별 평가.
UPDATE search_history
SET session_id = LOWER(CONCAT(
    SUBSTRING(HEX(RANDOM_BYTES(4)), 1, 8), '-',
    SUBSTRING(HEX(RANDOM_BYTES(2)), 1, 4), '-',
    '4', SUBSTRING(HEX(RANDOM_BYTES(2)), 1, 3), '-',
    SUBSTRING('89ab', 1 + FLOOR(RAND() * 4), 1), SUBSTRING(HEX(RANDOM_BYTES(2)), 1, 3), '-',
    SUBSTRING(HEX(RANDOM_BYTES(6)), 1, 12)
))
WHERE SUBSTRING(session_id, 15, 1) <> '4';
