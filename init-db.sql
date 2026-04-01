-- Create the mqtt_db_user with proper privileges
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mqtt_db_user') THEN
        CREATE USER mqtt_db_user WITH PASSWORD 'mqtt_db_password';
    END IF;
END
$$;

-- Grant connect privilege on database
GRANT CONNECT ON DATABASE mqtt_db TO mqtt_db_user;

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO mqtt_db_user;

-- Create mqtt_user table for CoMQTT authentication (matches Django model)
CREATE TABLE IF NOT EXISTS mqtt_user (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    allow SMALLINT DEFAULT 1 NOT NULL,
    created TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated TIMESTAMP WITH TIME ZONE
);

-- Create mqtt_acl table for CoMQTT access control
-- Uses username column for direct CoMQTT compatibility
CREATE TABLE IF NOT EXISTS mqtt_acl (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    access SMALLINT DEFAULT 2 NOT NULL,  -- 1=write, 2=read, 3=read+write
    created TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_acl_user FOREIGN KEY (username) REFERENCES mqtt_user(username) ON DELETE CASCADE
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_mqtt_acl_username ON mqtt_acl(username);
CREATE INDEX IF NOT EXISTS idx_mqtt_acl_topic ON mqtt_acl(topic);

-- Create mqtt_node table for device/node management
CREATE TABLE IF NOT EXISTS mqtt_node (
    id BIGSERIAL PRIMARY KEY,
    node_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    user_id BIGINT,
    location VARCHAR(255),
    status VARCHAR(20) DEFAULT 'active',
    created TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_node_user FOREIGN KEY (user_id) REFERENCES mqtt_user(id) ON DELETE SET NULL
);

-- Create index on mqtt_node
CREATE INDEX IF NOT EXISTS idx_mqtt_node_node_id ON mqtt_node(node_id);
CREATE INDEX IF NOT EXISTS idx_mqtt_node_user_id ON mqtt_node(user_id);

-- Grant table privileges to mqtt_db_user
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mqtt_db_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mqtt_db_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mqtt_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO mqtt_db_user;

-- Insert default admin user with bcrypt hashed password
-- Password: 'admin123' - hashed with bcrypt
-- You can generate a new hash with: python -c "import bcrypt; print(bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode())"
INSERT INTO mqtt_user (username, password, allow) VALUES 
    ('admin', '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjYDq.XRgO3hS1lKk1ZhQC68Nx9m10C', 1)
ON CONFLICT (username) DO NOTHING;

-- Insert a test user with bcrypt hashed password
-- Password: 'test123'
INSERT INTO mqtt_user (username, password, allow) VALUES 
    ('testuser', '$2b$10$LgXBW9Z3X9vOTQJq3D.LSeN7KQzQ.N1pXjYwVvXfNx9qyUztIVn5W', 1)
ON CONFLICT (username) DO NOTHING;

-- Insert ACL rules for admin user (full access to all topics)
INSERT INTO mqtt_acl (username, topic, access) VALUES 
    ('admin', '#', 3),
    ('admin', '$SYS/#', 3)
ON CONFLICT DO NOTHING;

-- Insert ACL rules for test user (access to test/# topics)
INSERT INTO mqtt_acl (username, topic, access) VALUES 
    ('testuser', 'test/#', 3),
    ('testuser', 'data/testuser/#', 3)
ON CONFLICT DO NOTHING;
