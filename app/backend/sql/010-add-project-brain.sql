CREATE TABLE IF NOT EXISTS project_brain_entries (
    id VARCHAR(64) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    origin VARCHAR(16) NOT NULL DEFAULT 'user',
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    source_ref VARCHAR(512) NOT NULL DEFAULT '',
    evidence JSON NOT NULL DEFAULT '[]',
    locked BOOLEAN NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_project_brain_entries_project_id ON project_brain_entries(project_id);
CREATE INDEX IF NOT EXISTS ix_project_brain_entries_category ON project_brain_entries(category);
CREATE INDEX IF NOT EXISTS ix_project_brain_project_category_status ON project_brain_entries(project_id, category, status);
CREATE INDEX IF NOT EXISTS ix_project_brain_project_locked ON project_brain_entries(project_id, locked);
