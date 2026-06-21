-- notice_category 에 화면 배지로 표시할 실제 문서 종류(doc_type) 컬럼 추가.
-- 기존엔 프론트가 category 로 배지를 추론(regulation→규정, 그 외→절차)했으나,
-- 원본 문서는 둘 다 공고/참고자료 성격이라 어긋났다(PRD §10 reference 배지 이슈 해소).
ALTER TABLE notice_category ADD COLUMN doc_type VARCHAR(20) NOT NULL DEFAULT '공고';

UPDATE notice_category SET doc_type = '공고'     WHERE `key` = 'regulation';
UPDATE notice_category SET doc_type = '참고자료' WHERE `key` = 'reference';
