package postgresql

import (
	"io"
	"log/slog"
	"net"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/wind-c/comqtt/v2/mqtt"
	"github.com/wind-c/comqtt/v2/mqtt/hooks/auth"
	"github.com/wind-c/comqtt/v2/mqtt/packets"
	"github.com/wind-c/comqtt/v2/plugin"
	pa "github.com/wind-c/comqtt/v2/plugin/auth"
)

const path = "./testdata/conf.yml"

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

	pkc = packets.Packet{Connect: packets.ConnectParams{Password: []byte("321654")}}
)

func teardown(a *Auth, t *testing.T) {
	if a.db != nil {
		a.Stop()
	}
}

func newAuth(t *testing.T) *Auth {
	return newGroupAuth(t, pa.GroupTable{})
}

func newGroupAuth(t *testing.T, group pa.GroupTable) *Auth {
	a := new(Auth)
	a.SetOpts(logger, nil)

	err := a.Init(&Options{
		AuthMode: byte(auth.AuthUsername),
		AclMode:  byte(auth.AuthUsername),
		Group:    group,
		Dsn: DsnInfo{
			Host:          "localhost",
			Port:          5432,
			Schema:        "comqtt",
			SslMode:       "disable",
			LoginName:     "postgres",
			LoginPassword: "12345678",
		},
		Auth: AuthTable{
			Table:          "auth",
			UserColumn:     "username",
			PasswordColumn: "password",
			AllowColumn:    "allow",
		},
		Acl: AclTable{
			Table:        "acl",
			UserColumn:   "username",
			TopicColumn:  "topic",
			AccessColumn: "access",
		},
	})
	require.NoError(t, err)

	return a
}

func TestInitFromConfFile(t *testing.T) {
	if !hasPostgresql() {
		t.Skip("no postgresql server running")
	}
	a := new(Auth)
	a.SetOpts(logger, nil)
	opts := Options{}
	err := plugin.LoadYaml(path, &opts)
	require.NoError(t, err)

	err = a.Init(&opts)
	require.NoError(t, err)
}

func TestInitBadConfig(t *testing.T) {
	a := new(Auth)
	a.SetOpts(logger, nil)

	err := a.Init(map[string]any{})
	require.Error(t, err)
}

func TestOnConnectAuthenticate(t *testing.T) {
	if !hasPostgresql() {
		t.Skip("no postgresql server running")
	}
	a := newAuth(t)
	defer teardown(a, t)
	result := a.OnConnectAuthenticate(client, pkc)
	require.Equal(t, true, result)
}

func TestOnACLCheck(t *testing.T) {
	if !hasPostgresql() {
		t.Skip("no postgresql server running")
	}
	a := newAuth(t)
	defer teardown(a, t)
	topic := "topictest/1"
	topic2 := "topictest/2"
	result := a.OnACLCheck(client, topic, true) //publish
	require.Equal(t, true, result)
	result = a.OnACLCheck(client, topic, false) //subscribe
	require.Equal(t, false, result)
	result = a.OnACLCheck(client, topic2, true)
	require.Equal(t, false, result)
	result = a.OnACLCheck(client, topic2, false)
	require.Equal(t, false, result)
}

func TestOnACLCheckGroups(t *testing.T) {
	if !hasPostgresql() {
		t.Skip("no postgresql server running")
	}
	a := newGroupAuth(t, pa.GroupTable{
		MemberTable: "user_group",
		AclTable:    "group_acl",
	})
	defer teardown(a, t)

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
}

func TestOnACLCheckGroupsDisabled(t *testing.T) {
	if !hasPostgresql() {
		t.Skip("no postgresql server running")
	}
	a := newAuth(t)
	defer teardown(a, t)
	require.False(t, a.OnACLCheck(client, "sensors/a/temp", false))
}

// hasPostgresql does a TCP connect to port 3306 to see if there is a MySQL server running on localhost.
func hasPostgresql() bool {
	c, err := net.Dial("tcp", "localhost:5432")
	if err != nil {
		return false
	}
	_ = c.Close()
	return true
}
