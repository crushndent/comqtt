package redis

import (
	"context"
	"io"
	"log/slog"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/stretchr/testify/require"
	"github.com/wind-c/comqtt/v2/mqtt"
	"github.com/wind-c/comqtt/v2/mqtt/hooks/auth"
	"github.com/wind-c/comqtt/v2/mqtt/packets"
)

var (
	// Currently, the input is directed to /dev/null. If you need to
	// output to stdout, just modify 'io.Discard' here to 'os.Stdout'.
	logger = slog.New(slog.NewTextHandler(io.Discard, nil))

	client = &mqtt.Client{
		ID: "test",
		Net: mqtt.ClientConnection{
			Remote:   "test.addr",
			Listener: "listener",
		},
		Properties: mqtt.ClientProperties{
			Username: []byte("zhangsan"),
			Clean:    false,
		},
	}

	//pkf = packets.Packet{Filters: packets.Subscriptions{{Filter: "a/b/c"}}}

	pkc = packets.Packet{Connect: packets.ConnectParams{Password: []byte("123456")}}
)

func newAuth(t *testing.T, addr string) *Auth {
	a := new(Auth)
	a.SetOpts(logger, nil)

	err := a.Init(&Options{
		AuthMode: byte(auth.AuthUsername),
		AclMode:  byte(auth.AuthUsername),
		RedisOptions: &redisOptions{
			Addr: addr,
		},
	})
	require.NoError(t, err)

	return a
}

func teardown(t *testing.T, a *Auth) {
	if a.db != nil {
		err := a.db.FlushAll(a.ctx).Err()
		require.NoError(t, err)
		a.Stop()
	}
}

func TestInitUseDefaults(t *testing.T) {
	s := miniredis.RunT(t)
	s.StartAddr(defaultAddr)
	defer s.Close()

	a := newAuth(t, defaultAddr)
	a.SetOpts(logger, nil)
	err := a.Init(nil)
	require.NoError(t, err)
	defer teardown(t, a)

	require.Equal(t, defaultAuthkeyPrefix, a.config.AuthKeyPrefix)
	require.Equal(t, defaultAddr, a.config.RedisOptions.Addr)
}

func TestInitBadConfig(t *testing.T) {
	a := new(Auth)
	a.SetOpts(logger, nil)

	err := a.Init(map[string]any{})
	require.Error(t, err)
}

func TestInitBadAddr(t *testing.T) {
	a := new(Auth)
	a.SetOpts(logger, nil)
	err := a.Init(&Options{
		RedisOptions: &redisOptions{
			Addr: "abc:123",
		},
	})
	require.Error(t, err)
}

func TestOnConnectAuthenticate(t *testing.T) {
	s := miniredis.RunT(t)
	defer s.Close()
	a := newAuth(t, s.Addr())
	defer teardown(t, a)

	user := "zhangsan"
	password := "123456"
	err := a.db.HSet(context.Background(), a.config.AuthKeyPrefix, user, auth.AuthRule{Allow: true, Password: auth.RString(password)}).Err()
	require.NoError(t, err)
	result := a.OnConnectAuthenticate(client, pkc)
	require.Equal(t, true, result)
}

func TestOnACLCheck(t *testing.T) {
	s := miniredis.RunT(t)
	defer s.Close()
	a := newAuth(t, s.Addr())
	defer teardown(t, a)

	user := "zhangsan"
	topic1 := "topictest/1"
	topic2 := "topictest/2"
	err := a.db.HSet(context.Background(), a.getAclKey(user), topic1, byte(auth.WriteOnly)).Err()
	require.NoError(t, err)
	result := a.OnACLCheck(client, topic1, true) //publish
	require.Equal(t, true, result)
	result = a.OnACLCheck(client, topic1, false) //subscribe
	require.Equal(t, false, result)
	result = a.OnACLCheck(client, topic2, true)
	require.Equal(t, false, result)
	result = a.OnACLCheck(client, topic2, false)
	require.Equal(t, false, result)

	a.db.HSet(context.Background(), a.getAclKey(user), topic2, byte(auth.ReadWrite)).Err()
	result = a.OnACLCheck(client, topic2, true) //publish
	require.Equal(t, true, result)
	result = a.OnACLCheck(client, topic2, false) //subscribe
	require.Equal(t, true, result)
}

func TestOnACLCheckGroups(t *testing.T) {
	s := miniredis.RunT(t)
	defer s.Close()
	a := new(Auth)
	a.SetOpts(logger, nil)
	err := a.Init(&Options{
		AuthMode:       byte(auth.AuthUsername),
		AclMode:        byte(auth.AuthUsername),
		GroupKeyPrefix: "comqtt:group",
		RedisOptions:   &redisOptions{Addr: s.Addr()},
	})
	require.NoError(t, err)
	defer teardown(t, a)
	require.Equal(t, defaultGroupAclKeyPrefix, a.config.GroupAclKeyPrefix)

	ctx := context.Background()
	require.NoError(t, a.db.HSet(ctx, a.getAclKey("zhangsan"), "topictest/1", byte(auth.WriteOnly)).Err())
	require.NoError(t, a.db.SAdd(ctx, a.getGroupKey("zhangsan"), "sensors", "sparkplug").Err())
	require.NoError(t, a.db.HSet(ctx, a.getGroupAclKey("sensors"),
		"topictest/1", byte(auth.ReadWrite),
		"sensors/#", byte(auth.ReadOnly),
		"sensors/+/cmd", byte(auth.WriteOnly),
		"shared/x", byte(auth.ReadOnly)).Err())
	require.NoError(t, a.db.HSet(ctx, a.getGroupAclKey("sparkplug"),
		"shared/x", byte(auth.WriteOnly),
		"spBv1.0/plant1/#", byte(auth.ReadWrite)).Err())
	require.NoError(t, a.db.HSet(ctx, a.getGroupAclKey("nobody"), "secret/#", byte(auth.ReadWrite)).Err())

	tt := []struct {
		topic string
		write bool
		want  bool
	}{
		{"topictest/1", true, true},               // user rule
		{"topictest/1", false, false},             // user rule wins over the group's ReadWrite
		{"topictest/2", true, false},              // no rule
		{"sensors/a/temp", false, true},           // group ReadOnly
		{"sensors/a/temp", true, false},           // group ReadOnly
		{"sensors/a/cmd", true, true},             // more specific group WriteOnly
		{"sensors/a/cmd", false, false},           // more specific group WriteOnly
		{"sensors/#", false, true},                // wildcard subscription inside the grant
		{"$share/g1/sensors/+/temp", false, true}, // shared subscription
		{"#", false, false},                       // wildcard subscription wider than any grant
		{"shared/x", false, true},                 // ReadOnly from one group
		{"shared/x", true, true},                  // WriteOnly from another group
		{"spBv1.0/plant1/NBIRTH/edge1", true, true},
		{"spBv1.0/plant1/DDATA/edge1/dev1", false, true},
		{"spBv1.0/plant2/NBIRTH/edge1", true, false},
		{"spBv1.0/#", false, false},
		{"secret/a", false, false}, // granted to a group the user is not in
	}
	for _, tx := range tt {
		require.Equal(t, tx.want, a.OnACLCheck(client, tx.topic, tx.write), "topic %s write %v", tx.topic, tx.write)
	}

	// a user without groups or rules is denied
	other := &mqtt.Client{Properties: mqtt.ClientProperties{Username: []byte("lisi")}}
	require.False(t, a.OnACLCheck(other, "sensors/a/temp", false))
}

func TestOnACLCheckGroupsDisabled(t *testing.T) {
	s := miniredis.RunT(t)
	defer s.Close()
	a := newAuth(t, s.Addr())
	defer teardown(t, a)

	ctx := context.Background()
	require.NoError(t, a.db.SAdd(ctx, "comqtt:group:zhangsan", "sensors").Err())
	require.NoError(t, a.db.HSet(ctx, defaultGroupAclKeyPrefix+":sensors", "sensors/#", byte(auth.ReadOnly)).Err())
	require.False(t, a.OnACLCheck(client, "sensors/a/temp", false))
}
