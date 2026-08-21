-- 009 项目级资产隔离：给 scenes/props/costumes/actors 加 project_id，
-- 从对应 project_*_links 回填，唯一约束从 (name) 改为 (project_id, name)。
-- 幂等：可重复执行（mysql-init-sql 每次启动全量重跑）。

-- ========== scenes ==========
SET @has := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='scenes' AND COLUMN_NAME='project_id');
SET @s := IF(@has=0, "ALTER TABLE scenes ADD COLUMN project_id VARCHAR(64) NULL COMMENT '所属项目ID', ADD INDEX ix_scenes_project_id (project_id)", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
UPDATE scenes sc JOIN (SELECT scene_id, MIN(project_id) pid FROM project_scene_links GROUP BY scene_id) l ON l.scene_id=sc.id SET sc.project_id=l.pid WHERE sc.project_id IS NULL;
SET @hu := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='scenes' AND CONSTRAINT_NAME='uq_scenes_name');
SET @s := IF(@hu>0, "ALTER TABLE scenes DROP INDEX uq_scenes_name", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @hu2 := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='scenes' AND CONSTRAINT_NAME='uq_scenes_project_name');
SET @s := IF(@hu2=0, "ALTER TABLE scenes ADD CONSTRAINT uq_scenes_project_name UNIQUE (project_id, name)", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ========== props ==========
SET @has := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='props' AND COLUMN_NAME='project_id');
SET @s := IF(@has=0, "ALTER TABLE props ADD COLUMN project_id VARCHAR(64) NULL COMMENT '所属项目ID', ADD INDEX ix_props_project_id (project_id)", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
UPDATE props pr JOIN (SELECT prop_id, MIN(project_id) pid FROM project_prop_links GROUP BY prop_id) l ON l.prop_id=pr.id SET pr.project_id=l.pid WHERE pr.project_id IS NULL;
SET @hu := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='props' AND CONSTRAINT_NAME='uq_props_name');
SET @s := IF(@hu>0, "ALTER TABLE props DROP INDEX uq_props_name", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @hu2 := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='props' AND CONSTRAINT_NAME='uq_props_project_name');
SET @s := IF(@hu2=0, "ALTER TABLE props ADD CONSTRAINT uq_props_project_name UNIQUE (project_id, name)", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ========== costumes ==========
SET @has := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='costumes' AND COLUMN_NAME='project_id');
SET @s := IF(@has=0, "ALTER TABLE costumes ADD COLUMN project_id VARCHAR(64) NULL COMMENT '所属项目ID', ADD INDEX ix_costumes_project_id (project_id)", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
UPDATE costumes co JOIN (SELECT costume_id, MIN(project_id) pid FROM project_costume_links GROUP BY costume_id) l ON l.costume_id=co.id SET co.project_id=l.pid WHERE co.project_id IS NULL;
SET @hu := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='costumes' AND CONSTRAINT_NAME='uq_costumes_name');
SET @s := IF(@hu>0, "ALTER TABLE costumes DROP INDEX uq_costumes_name", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @hu2 := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='costumes' AND CONSTRAINT_NAME='uq_costumes_project_name');
SET @s := IF(@hu2=0, "ALTER TABLE costumes ADD CONSTRAINT uq_costumes_project_name UNIQUE (project_id, name)", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ========== actors ==========
SET @has := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='actors' AND COLUMN_NAME='project_id');
SET @s := IF(@has=0, "ALTER TABLE actors ADD COLUMN project_id VARCHAR(64) NULL COMMENT '所属项目ID', ADD INDEX ix_actors_project_id (project_id)", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
UPDATE actors ac JOIN (SELECT actor_id, MIN(project_id) pid FROM project_actor_links GROUP BY actor_id) l ON l.actor_id=ac.id SET ac.project_id=l.pid WHERE ac.project_id IS NULL;
SET @hu := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='actors' AND CONSTRAINT_NAME='uq_actors_name');
SET @s := IF(@hu>0, "ALTER TABLE actors DROP INDEX uq_actors_name", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @hu2 := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='actors' AND CONSTRAINT_NAME='uq_actors_project_name');
SET @s := IF(@hu2=0, "ALTER TABLE actors ADD CONSTRAINT uq_actors_project_name UNIQUE (project_id, name)", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
