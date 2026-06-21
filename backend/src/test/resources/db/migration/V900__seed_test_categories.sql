-- 테스트 전용 시드(운영 마이그레이션 아님). diff 통합테스트가 다른 테스트의
-- regulation/reference 데이터와 충돌하지 않도록 전용 카테고리를 둔다.
-- 높은 버전(V900)으로 두어 향후 운영 마이그레이션(V3, V4 ...)과 충돌하지 않는다.
INSERT INTO notice_category (`key`, label, doc_title) VALUES
  ('difftest', 'diff 테스트', 'diff 통합테스트 전용 카테고리'),
  ('datetest', '시행일 테스트', '시행일(백데이트) 검증 전용 카테고리');
