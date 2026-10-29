BEGIN;

CREATE TABLE auth (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    allow SMALLINT DEFAULT 1 NOT NULL,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated TIMESTAMP NULL
);

CREATE TABLE acl (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    access SMALLINT DEFAULT 3 NOT NULL,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated TIMESTAMP NULL
);

CREATE INDEX acl_username_idx ON acl(username);

-- optional group acl, enabled by the "group" section of the plugin config
CREATE TABLE user_group (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    groupname VARCHAR(255) NOT NULL,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY user_group_uidx (username, groupname)
);

CREATE TABLE group_acl (
    id INT AUTO_INCREMENT PRIMARY KEY,
    groupname VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    access SMALLINT DEFAULT 3 NOT NULL,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated TIMESTAMP NULL
);

CREATE INDEX group_acl_groupname_idx ON group_acl(groupname);

-- 123456
INSERT INTO auth (username, password, allow) VALUES ('zhangsan', '$2a$12$j8bs10UCRC5GUENPqZXLceACpN1l72wcDaN6F0j0rIbcHIZpt0Cbq', 1);
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
