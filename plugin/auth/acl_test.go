package auth

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/wind-c/comqtt/v2/mqtt/hooks/auth"
)

func TestTrimSharePrefix(t *testing.T) {
	require.Equal(t, "a/b", TrimSharePrefix("$share/g1/a/b"))
	require.Equal(t, "#", TrimSharePrefix("$share/g1/#"))
	require.Equal(t, "$share/g1", TrimSharePrefix("$share/g1"))
	require.Equal(t, "a/b", TrimSharePrefix("a/b"))
}

func TestMatchAcl(t *testing.T) {
	tt := []struct {
		rule  string
		topic string
		want  bool
	}{
		// publish topics
		{"a/b", "a/b", true},
		{"a/b", "a/b/c", false},
		{"a/b", "a", false},
		{"a/+", "a/b", true},
		{"a/+", "a/b/c", false},
		{"a/+/c", "a/b/c", true},
		{"a/#", "a", true},
		{"a/#", "a/b/c", true},
		{"#", "a/b", true},
		// subscription filters must not be wider than the rule
		{"a/b", "a/#", false},
		{"a/b", "#", false},
		{"a/b", "a/+", false},
		{"a/+", "a/#", false},
		{"a/+", "a/+", true},
		{"a/#", "a/+", true},
		{"a/#", "a/#", true},
		{"a/#", "a/+/c", true},
		{"a/+/c", "a/+/c", true},
		{"a/+/c", "a/+/+", false},
		{"#", "#", true},
		// shared subscriptions are checked on the subscribed filter
		{"a/b", "$share/g1/a/b", true},
		{"a/#", "$share/g1/a/b", true},
		{"a/b", "$share/g1/a/#", false},
		// sparkplug b namespace
		{"spBv1.0/plant1/#", "spBv1.0/plant1/NBIRTH/edge1", true},
		{"spBv1.0/plant1/#", "spBv1.0/plant1/DDATA/edge1/dev1", true},
		{"spBv1.0/plant1/#", "spBv1.0/plant2/NBIRTH/edge1", false},
		{"spBv1.0/plant1/#", "spBv1.0/#", false},
		{"spBv1.0/+/#", "spBv1.0/#", false},
		{"spBv1.0/+/#", "spBv1.0/+/DDATA/#", true},
		{"spBv1.0/STATE/+", "spBv1.0/STATE/scada1", true},
		{"spBv1.0/STATE/+", "spBv1.0/STATE/#", false},
	}

	for _, tx := range tt {
		require.Equal(t, tx.want, MatchAcl(tx.rule, tx.topic), "rule %s topic %s", tx.rule, tx.topic)
	}
}

func TestCheckAclMostSpecificWins(t *testing.T) {
	fam := map[string]auth.Access{"a/#": auth.ReadWrite, "a/b/delete": auth.Deny}
	require.False(t, CheckAcl(fam, true))
	fam = map[string]auth.Access{"a/#": auth.Deny, "a/b/find": auth.ReadOnly}
	require.True(t, CheckAcl(fam, false))
	require.False(t, CheckAcl(fam, true))
	require.False(t, CheckAcl(map[string]auth.Access{}, false))
}

func TestCheckAclTieDenies(t *testing.T) {
	// equally long filters that both match conflict; the result must not
	// depend on map iteration order
	fam := map[string]auth.Access{"a/+/c": auth.ReadWrite, "a/b/#": auth.Deny}
	for i := 0; i < 100; i++ {
		require.False(t, CheckAcl(fam, true))
	}
}
