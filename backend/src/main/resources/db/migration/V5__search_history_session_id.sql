-- 채팅 기록을 URL(/q/<session_id>)로 식별하기 위한 UUID 세션 id.
-- 기존 행은 UUID() 로 백필한 뒤 NOT NULL·UNIQUE 로 승격한다(신규 행은 앱에서 UUIDv4 부여).
ALTER TABLE search_history ADD COLUMN session_id VARCHAR(36) NULL AFTER id;
UPDATE search_history SET session_id = UUID() WHERE session_id IS NULL;
ALTER TABLE search_history MODIFY COLUMN session_id VARCHAR(36) NOT NULL;
ALTER TABLE search_history ADD CONSTRAINT uq_search_history_session UNIQUE (session_id);
