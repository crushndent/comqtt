package auth

import (
	"database/sql"
	"strings"

	"github.com/wind-c/comqtt/v2/mqtt/hooks/auth"
)

const sharePrefix = "$share/"

// TrimSharePrefix removes the "$share/<group>/" prefix of a shared subscription,
// so that ACL rules are checked against the filter that is actually subscribed.
func TrimSharePrefix(filter string) string {
	if !strings.HasPrefix(filter, sharePrefix) {
		return filter
	}
	parts := strings.SplitN(filter, "/", 3)
	if len(parts) < 3 {
		return filter
	}
	return parts[2]
}

// MatchAcl returns true if the ACL rule filter covers the given topic.
// When subscribing, topic is a subscription filter that may itself contain
// wildcards; it is only covered if every topic it could match is also matched
// by the rule. Eg. rule a/# covers a, a/b and a/+/c, rule a/+ does not cover a/#.
func MatchAcl(rule, topic string) bool {
	rp := strings.Split(TrimSharePrefix(rule), "/")
	tp := strings.Split(TrimSharePrefix(topic), "/")

	for i := 0; i < len(rp); i++ {
		if rp[i] == "#" {
			return true
		}
		if i >= len(tp) || tp[i] == "#" {
			return false
		}
		if rp[i] == "+" {
			continue
		}
		if rp[i] != tp[i] {
			return false
		}
	}

	return len(rp) == len(tp)
}

// CollectAcl reads (filter, access) rows and adds those matching topic to fam.
// With merge set, grants on the same filter are combined (see MergeAccess).
func CollectAcl(rows *sql.Rows, topic string, fam map[string]auth.Access, merge bool) error {
	defer rows.Close()
	for rows.Next() {
		var filter string
		var access byte
		if err := rows.Scan(&filter, &access); err != nil {
			continue
		}

		if !MatchAcl(filter, topic) {
			continue
		}

		if merge {
			MergeAccess(fam, filter, auth.Access(access))
		} else {
			fam[filter] = auth.Access(access)
		}
	}
	return rows.Err()
}
