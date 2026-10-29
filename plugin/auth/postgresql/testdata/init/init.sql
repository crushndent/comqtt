BEGIN;
CREATE TABLE auth (
    id serial PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    allow smallint DEFAULT 1 NOT NULL,
    created timestamp with time zone DEFAULT NOW(),
    updated timestamp
);

CREATE TABLE acl(
    id serial PRIMARY KEY,
    username TEXT NOT NULL,
    topic TEXT NOT NULL,
    access smallint DEFAULT 3 NOT NULL,
    created timestamp with time zone DEFAULT NOW(),
    updated timestamp
);
CREATE INDEX acl_username_idx ON acl(username);

-- optional group acl, enabled by the "group" section of the plugin config
CREATE TABLE user_group(
    id serial PRIMARY KEY,
    username TEXT NOT NULL,
    groupname TEXT NOT NULL,
    created timestamp with time zone DEFAULT NOW(),
    UNIQUE (username, groupname)
);

CREATE TABLE group_acl(
    id serial PRIMARY KEY,
    groupname TEXT NOT NULL,
    topic TEXT NOT NULL,
    access smallint DEFAULT 3 NOT NULL,
    created timestamp with time zone DEFAULT NOW(),
    updated timestamp
);
CREATE INDEX group_acl_groupname_idx ON group_acl(groupname);

INSERT INTO auth (username, password, allow) VALUES ('zhangsan', '321654', 1);
INSERT INTO acl (username, topic, access) VALUES ('zhangsan', 'topictest/1', 2);

INSERT INTO user_group (username, groupname) VALUES ('zhangsan', 'sensors'), ('zhangsan', 'sparkplug');
INSERT INTO group_acl (groupname, topic, access) VALUES
    ('sensors', 'topictest/1', 3),
    ('sensors', 'sensors/#', 1),
    ('sensors', 'sensors/+/cmd', 2),
    ('sensors', 'shared/x', 1),
    ('sparkplug', 'shared/x', 2),
    ('sparkplug', 'spBv1.0/plant1/#', 3),
    ('nobody', 'secret/#', 3);

COMMIT;
