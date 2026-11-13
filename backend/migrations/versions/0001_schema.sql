CREATE EXTENSION IF NOT EXISTS vector;


CREATE TABLE deletion_requests (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	subject VARCHAR(128) NOT NULL, 
	request_id VARCHAR(36) NOT NULL, 
	resource_type VARCHAR(30) NOT NULL, 
	resource_id VARCHAR(36) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	error_code VARCHAR(80), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, request_id)
)

;

CREATE INDEX ix_deletion_requests_user_id ON deletion_requests (user_id);


CREATE TABLE jobs (
	id VARCHAR(36) NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	resource_id VARCHAR(36) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	error_code VARCHAR(80), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_jobs_resource_id ON jobs (resource_id);


CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	subject VARCHAR(128) NOT NULL, 
	display_name VARCHAR(120) NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (subject)
)

;


CREATE TABLE conversations (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	title VARCHAR(120) NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	document_ids JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_conversations_user_id ON conversations (user_id);


CREATE TABLE documents (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	mime VARCHAR(100) NOT NULL, 
	bytes INTEGER NOT NULL, 
	object_key VARCHAR(400) NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	version INTEGER NOT NULL, 
	error_code VARCHAR(80), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_documents_user_id ON documents (user_id);


CREATE TABLE document_chunks (
	id VARCHAR(36) NOT NULL, 
	document_id VARCHAR(36) NOT NULL, 
	version INTEGER NOT NULL, 
	ordinal INTEGER NOT NULL, 
	page INTEGER, 
	content TEXT NOT NULL, 
	embedding vector(1536) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (document_id, version, ordinal), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_document_chunks_document_id ON document_chunks (document_id);


CREATE TABLE messages (
	id VARCHAR(36) NOT NULL, 
	conversation_id VARCHAR(36) NOT NULL, 
	sequence INTEGER NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (conversation_id, sequence), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_messages_conversation_id ON messages (conversation_id);


CREATE TABLE generations (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	conversation_id VARCHAR(36) NOT NULL, 
	user_message_id VARCHAR(36) NOT NULL, 
	assistant_message_id VARCHAR(36) NOT NULL, 
	request_id VARCHAR(36) NOT NULL, 
	payload_hash VARCHAR(64) NOT NULL, 
	model_id VARCHAR(160) NOT NULL, 
	provider VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	sources JSONB NOT NULL, 
	document_versions JSONB NOT NULL, 
	cancel_requested BOOLEAN NOT NULL, 
	error_code VARCHAR(60), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, request_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_message_id) REFERENCES messages (id) ON DELETE CASCADE, 
	FOREIGN KEY(assistant_message_id) REFERENCES messages (id) ON DELETE CASCADE
)

;

CREATE UNIQUE INDEX one_active_generation ON generations (conversation_id) WHERE status IN ('pending','streaming');

CREATE INDEX ix_generations_conversation_id ON generations (conversation_id);

CREATE INDEX ix_generations_user_id ON generations (user_id);


CREATE TABLE usage_events (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	conversation_id VARCHAR(36), 
	generation_id VARCHAR(36), 
	document_id VARCHAR(36), 
	provider VARCHAR(20) NOT NULL, 
	model_id VARCHAR(160) NOT NULL, 
	operation VARCHAR(30) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	cached_tokens INTEGER, 
	cost_usd NUMERIC(20, 10), 
	rate JSONB NOT NULL, 
	provider_request_id VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE SET NULL, 
	FOREIGN KEY(generation_id) REFERENCES generations (id) ON DELETE SET NULL, 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE SET NULL
)

;

CREATE INDEX ix_usage_events_user_id ON usage_events (user_id);
