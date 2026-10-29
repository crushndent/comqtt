package redis

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"strconv"

	"github.com/redis/go-redis/v9"
	"github.com/wind-c/comqtt/v2/mqtt"
	"github.com/wind-c/comqtt/v2/mqtt/hooks/auth"
	"github.com/wind-c/comqtt/v2/mqtt/packets"
	pa "github.com/wind-c/comqtt/v2/plugin/auth"
)

// defaultAddr is the default address to the redis service.
const defaultAddr = "localhost:6379"

// defaultAuthPrefix is a prefix to better identify hsets created by comqtt.
const defaultAuthkeyPrefix = "comqtt:auth"

// defaultAclPrefix is a prefix to better identify hsets created by comqtt.
const defaultAclKeyPrefix = "comqtt:acl"

// defaultGroupAclKeyPrefix is the default prefix of group acl hsets, used when group acl is enabled.
const defaultGroupAclKeyPrefix = "comqtt:group-acl"

type Options struct {
	pa.Blacklist
	RedisOptions  *redisOptions `json:"redis-options" yaml:"redis-options"`
	AuthMode      byte          `json:"auth-mode" yaml:"auth-mode"`
	AuthKeyPrefix string        `json:"auth-prefix" yaml:"auth-prefix"`
	AclMode       byte          `json:"acl-mode" yaml:"acl-mode"`
	AclKeyPrefix  string        `json:"acl-prefix" yaml:"acl-prefix"`
	PasswordHash  pa.HashType   `json:"password-hash" yaml:"password-hash"`
	HashKey       string        `json:"hash-key" yaml:"hash-key"`
	// GroupKeyPrefix enables group acl when set: the set <group-prefix>:<user> holds the user's groups.
	GroupKeyPrefix string `json:"group-prefix" yaml:"group-prefix"`
	// GroupAclKeyPrefix is the prefix of the hset <group-acl-prefix>:<group> holding a group's topic rules.
	GroupAclKeyPrefix string `json:"group-acl-prefix" yaml:"group-acl-prefix"`
	//Blacklist     auth.Ledger   `json:"blacklist" yaml:"blacklist"`
}

type redisOptions struct {
	Addr     string `json:"addr" yaml:"addr"`
	Username string `json:"username" yaml:"username"`
	Password string `json:"password" yaml:"password"`
	DB       int    `json:"db" yaml:"db"`
}

// Auth is an auth controller which allows access to all connections and topics.
type Auth struct {
	mqtt.HookBase
	config *Options
	db     *redis.Client
	ctx    context.Context // a context for the connection
}

// ID returns the ID of the hook.
func (a *Auth) ID() string {
	return "auth-redis"
}

// Provides indicates which hook methods this hook provides.
func (a *Auth) Provides(b byte) bool {
	return bytes.Contains([]byte{
		mqtt.OnConnectAuthenticate,
		mqtt.OnACLCheck,
	}, []byte{b})
}

func (a *Auth) Init(config any) error {
	if _, ok := config.(*Options); !ok && config != nil {
		return mqtt.ErrInvalidConfigType
	}

	a.ctx = context.Background()

	if config == nil {
		config = &Options{
			RedisOptions: &redisOptions{
				Addr: defaultAddr,
			},
		}
	}

	a.config = config.(*Options)
	if a.config.AuthKeyPrefix == "" {
		a.config.AuthKeyPrefix = defaultAuthkeyPrefix
	}
	if a.config.AclKeyPrefix == "" {
		a.config.AclKeyPrefix = defaultAclKeyPrefix
	}
	if a.config.GroupKeyPrefix != "" && a.config.GroupAclKeyPrefix == "" {
		a.config.GroupAclKeyPrefix = defaultGroupAclKeyPrefix
	}

	a.Log.Info("connecting to redis service",
		"address", a.config.RedisOptions.Addr, "username", a.config.RedisOptions.Username,
		"password-len", len(a.config.RedisOptions.Password),
		"db", a.config.RedisOptions.DB)

	a.db = redis.NewClient(&redis.Options{
		Addr:     a.config.RedisOptions.Addr,
		Username: a.config.RedisOptions.Username,
		Password: a.config.RedisOptions.Password,
		DB:       a.config.RedisOptions.DB,
	})
	_, err := a.db.Ping(context.Background()).Result()
	if err != nil {
		return fmt.Errorf("failed to ping service: %w", err)
	}

	a.Log.Info("connected to redis service")
	return nil
}

// Stop closes the redis connection.
func (a *Auth) Stop() error {
	a.Log.Info("disconnecting from redis service")
	return a.db.Close()
}

func (a *Auth) getAuthKey() string {
	return a.config.AuthKeyPrefix
}

func (a *Auth) getAclKey(uid string) string {
	return a.config.AclKeyPrefix + ":" + uid
}

func (a *Auth) getGroupKey(uid string) string {
	return a.config.GroupKeyPrefix + ":" + uid
}

func (a *Auth) getGroupAclKey(group string) string {
	return a.config.GroupAclKeyPrefix + ":" + group
}

// collectAcl adds the rules of res matching topic to fam.
func collectAcl(res map[string]string, topic string, fam map[string]auth.Access, merge bool) {
	for filter, rw := range res {
		if !pa.MatchAcl(filter, topic) {
			continue
		}

		access, err := strconv.Atoi(rw)
		if err != nil {
			continue
		}

		if merge {
			pa.MergeAccess(fam, filter, auth.Access(access))
		} else {
			fam[filter] = auth.Access(access)
		}
	}
}

// groupAcl returns the rules of all groups of a user matching topic.
func (a *Auth) groupAcl(key, topic string) (map[string]auth.Access, error) {
	gam := make(map[string]auth.Access)
	groups, err := a.db.SMembers(a.ctx, a.getGroupKey(key)).Result()
	if err != nil && err != redis.Nil {
		return nil, err
	}
	if len(groups) == 0 {
		return gam, nil
	}

	pipe := a.db.Pipeline()
	cmds := make([]*redis.MapStringStringCmd, len(groups))
	for i, g := range groups {
		cmds[i] = pipe.HGetAll(a.ctx, a.getGroupAclKey(g))
	}
	if _, err := pipe.Exec(a.ctx); err != nil && err != redis.Nil {
		return nil, err
	}

	for _, cmd := range cmds {
		collectAcl(cmd.Val(), topic, gam, true)
	}
	return gam, nil
}

// OnConnectAuthenticate returns true if the connecting client has rules which provide access
// in the auth ledger.
func (a *Auth) OnConnectAuthenticate(cl *mqtt.Client, pk packets.Packet) bool {
	if a.config.AuthMode == byte(auth.AuthAnonymous) {
		return true
	}

	// check blacklist
	if n, ok := a.config.CheckBLAuth(cl, pk); n >= 0 { // It's on the blacklist
		return ok
	}

	// normal verification
	var key string
	if a.config.AuthMode == byte(auth.AuthUsername) {
		key = string(cl.Properties.Username)
	} else if a.config.AuthMode == byte(auth.AuthClientID) {
		key = cl.ID
	} else {
		return false
	}

	res, err := a.db.HGet(context.Background(), a.getAuthKey(), key).Result()
	if err != nil && err != redis.Nil || res == "" {
		return false
	}

	var ar auth.AuthRule
	if err = json.Unmarshal([]byte(res), &ar); err != nil {
		a.Log.Error("failed to unmarshal redis auth data", "error", err, "data", res)
		return false
	}

	if !ar.Allow {
		return false
	}

	return pa.CompareHash(string(ar.Password), string(pk.Connect.Password), a.config.HashKey, a.config.PasswordHash)
}

// OnACLCheck returns true if the connecting client has matching read or write access to subscribe
// or publish to a given topic.
func (a *Auth) OnACLCheck(cl *mqtt.Client, topic string, write bool) bool {
	if a.config.AclMode == byte(auth.AuthAnonymous) {
		return true
	}

	// check blacklist
	if n, ok := a.config.CheckBLAcl(cl, topic, write); n >= 0 { // It's on the blacklist
		return ok
	}

	// normal verification
	var key string
	if a.config.AclMode == byte(auth.AuthUsername) {
		key = string(cl.Properties.Username)
	} else if a.config.AclMode == byte(auth.AuthClientID) {
		key = cl.ID
	} else {
		return false
	}

	res, err := a.db.HGetAll(context.Background(), a.getAclKey(key)).Result()
	if err != nil && err != redis.Nil {
		return false
	}

	fam := make(map[string]auth.Access)
	collectAcl(res, topic, fam, false)
	if len(fam) > 0 || a.config.GroupKeyPrefix == "" {
		return pa.CheckAcl(fam, write)
	}

	// no user rule matches, fall back to the rules of the user's groups
	gam, err := a.groupAcl(key, topic)
	if err != nil {
		return false
	}

	return pa.CheckUserGroupAcl(fam, gam, write)
}
