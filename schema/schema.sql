PRAGMA foreign_keys=ON;
CREATE TABLE source (
 source_id TEXT PRIMARY KEY,
 namespace TEXT NOT NULL CHECK(namespace IN ('archive','file','legacy','attachment')),
 external_id TEXT NOT NULL,
 content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
 raw_text TEXT NOT NULL,
 locator_json TEXT NOT NULL CHECK(json_valid(locator_json)),
 observed_at TEXT NOT NULL,
 schema_version INTEGER NOT NULL DEFAULT 1,
 archive_event_id TEXT, logical_event_id TEXT, source_event_id TEXT,
 source_event_sha256 TEXT, record_sha256 TEXT,
 agent_id TEXT NOT NULL DEFAULT 'personal', session_id TEXT, session_key TEXT,
 channel TEXT, conversation_identity TEXT, mime TEXT, selector_json TEXT NOT NULL DEFAULT '{}',
 file_sha256 TEXT, parent_source_id TEXT REFERENCES source(source_id),
 UNIQUE(namespace,external_id,content_sha256)
);
CREATE TABLE item (
 item_id TEXT PRIMARY KEY,
 kind TEXT NOT NULL,
 head_revision_id TEXT,
 created_at TEXT NOT NULL,
 FOREIGN KEY(head_revision_id,item_id) REFERENCES revision(revision_id,item_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE revision (
 revision_id TEXT PRIMARY KEY,
 item_id TEXT NOT NULL REFERENCES item(item_id),
 version INTEGER NOT NULL CHECK(version>0),
 parent_revision_id TEXT,
 action TEXT NOT NULL CHECK(action IN ('create','update','correction','supersede','soft_delete','restore')),
 status TEXT NOT NULL CHECK(status IN ('active','review','deleted')),
 domain TEXT NOT NULL,
 title TEXT NOT NULL,
 body TEXT NOT NULL,
 tags_json TEXT NOT NULL CHECK(json_valid(tags_json)),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 assertion_kind TEXT NOT NULL CHECK(assertion_kind IN ('user_report','third_party_report','user_judgment','user_feeling','ai_inference','unconfirmed','plan')),
 certainty TEXT NOT NULL CHECK(certainty IN ('stated','uncertain','unknown','retracted')),
 perspective TEXT NOT NULL CHECK(perspective IN ('user','third_party','ai')),
 temporal_status TEXT NOT NULL CHECK(temporal_status IN ('occurred','planned','unknown')),
 valid_from TEXT,
 valid_to TEXT,
 time_expression TEXT,
 time_precision TEXT NOT NULL CHECK(time_precision IN ('unknown','year','month','day','instant','range')),
 timezone TEXT NOT NULL,
 visibility TEXT NOT NULL CHECK(visibility IN ('private','restricted')),
 actor TEXT NOT NULL,
 reason TEXT NOT NULL,
 extraction_json TEXT NOT NULL CHECK(json_valid(extraction_json)),
 revision_sha256 TEXT NOT NULL CHECK(length(revision_sha256)=64),
 created_at TEXT NOT NULL,
 UNIQUE(item_id,version), UNIQUE(revision_id,item_id),
 FOREIGN KEY(parent_revision_id,item_id) REFERENCES revision(revision_id,item_id),
 CHECK(valid_to IS NULL OR valid_from IS NULL OR valid_to>=valid_from),
 CHECK(assertion_kind!='ai_inference' OR (perspective='ai' AND certainty IN ('uncertain','unknown') AND status='review')),
 CHECK(assertion_kind!='third_party_report' OR perspective='third_party'),
 CHECK(assertion_kind NOT IN ('user_feeling','user_judgment') OR perspective='user'),
 CHECK(assertion_kind!='plan' OR temporal_status='planned')
);
CREATE TABLE evidence (
 revision_id TEXT NOT NULL REFERENCES revision(revision_id),
 source_id TEXT NOT NULL REFERENCES source(source_id),
 role TEXT NOT NULL CHECK(role IN ('supports','corrects','context','contradicts')),
 quote TEXT NOT NULL,
 start_char INTEGER NOT NULL CHECK(start_char>=0),
 end_char INTEGER NOT NULL CHECK(end_char>=start_char),
 PRIMARY KEY(revision_id,source_id,role,start_char,end_char)
);
CREATE TABLE relation (
 revision_id TEXT NOT NULL REFERENCES revision(revision_id),
 ordinal INTEGER NOT NULL,
 subject_item_id TEXT NOT NULL REFERENCES item(item_id),
 predicate TEXT NOT NULL,
 object_item_id TEXT NOT NULL REFERENCES item(item_id),
 qualifiers_json TEXT NOT NULL CHECK(json_valid(qualifiers_json)),
 PRIMARY KEY(revision_id,ordinal)
);
CREATE TABLE entity_alias (
 revision_id TEXT NOT NULL REFERENCES revision(revision_id),
 entity_item_id TEXT NOT NULL REFERENCES item(item_id),
 alias TEXT NOT NULL,
 PRIMARY KEY(revision_id,alias)
);
CREATE INDEX alias_lookup ON entity_alias(alias);
CREATE TABLE operation (
 operation_key TEXT PRIMARY KEY,
 request_sha256 TEXT NOT NULL,
 actor TEXT NOT NULL,
 result_json TEXT NOT NULL CHECK(json_valid(result_json)),
 committed_at TEXT NOT NULL
);
CREATE TABLE task_detail (
 revision_id TEXT PRIMARY KEY REFERENCES revision(revision_id),
 state TEXT NOT NULL CHECK(state IN ('open','done','cancelled','paused')),
 due_date TEXT,
 due_expression TEXT,
 timezone TEXT NOT NULL
);
CREATE TABLE financial_detail (
 revision_id TEXT PRIMARY KEY REFERENCES revision(revision_id),
 amount_minor INTEGER NOT NULL CHECK(typeof(amount_minor)='integer' AND amount_minor>=0 AND amount_minor<=1000000000000),
 currency TEXT NOT NULL CHECK(length(currency)=3 AND currency=upper(currency)),
 scale INTEGER NOT NULL CHECK(scale BETWEEN 0 AND 6),
 direction TEXT NOT NULL CHECK(direction IN ('expense','income','refund')),
 entry_class TEXT NOT NULL CHECK(entry_class IN ('booked','quote','budget','commitment')),
 occurred_date TEXT
);
CREATE TABLE schedule_detail (
 revision_id TEXT PRIMARY KEY REFERENCES revision(revision_id),
 start_date TEXT,
 end_date TEXT,
 time_expression TEXT NOT NULL,
 timezone TEXT NOT NULL,
 CHECK(end_date IS NULL OR start_date IS NULL OR end_date>=start_date)
);
CREATE VIRTUAL TABLE current_fts USING fts5(item_id UNINDEXED, title, body, tokenize='trigram');
CREATE VIEW current_item AS
 SELECT i.item_id,i.kind,r.* FROM item i JOIN revision r ON r.revision_id=i.head_revision_id WHERE r.status='active';
CREATE INDEX revision_date_domain ON revision(valid_from,domain);
CREATE INDEX evidence_source ON evidence(source_id);
CREATE INDEX relation_object ON relation(object_item_id);
CREATE TRIGGER item_identity_immutable BEFORE UPDATE OF item_id,kind,created_at ON item BEGIN SELECT RAISE(ABORT,'immutable item identity'); END;
CREATE TRIGGER item_no_delete BEFORE DELETE ON item BEGIN SELECT RAISE(ABORT,'use revision soft_delete'); END;
CREATE TRIGGER immutable_source_update BEFORE UPDATE ON source BEGIN SELECT RAISE(ABORT,'immutable source'); END;
CREATE TRIGGER immutable_source_delete BEFORE DELETE ON source BEGIN SELECT RAISE(ABORT,'immutable source'); END;

CREATE TABLE pending_intent(intent_id TEXT PRIMARY KEY,kind TEXT NOT NULL,ctx_json TEXT NOT NULL,args_json TEXT NOT NULL,binding_json TEXT,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL,created_at REAL NOT NULL,last_error TEXT,result_json TEXT);
CREATE TABLE origin_item(archive_event_id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES source(source_id),item_id TEXT NOT NULL REFERENCES item(item_id),is_fallback INTEGER NOT NULL);
CREATE TABLE worker_checkpoint(session_id TEXT PRIMARY KEY,seq INTEGER NOT NULL);
CREATE TABLE migration(version INTEGER PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL);
