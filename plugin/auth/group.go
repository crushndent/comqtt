package auth

import (
	"fmt"

	"github.com/wind-c/comqtt/v2/mqtt/hooks/auth"
)

// MergeAccess adds a grant to an access map. Grants on the same filter from
// several groups are combined, eg. ReadOnly from one group and WriteOnly from
// another give ReadWrite.
func MergeAccess(fam map[string]auth.Access, filter string, access auth.Access) {
	fam[filter] |= access
}

// CheckUserGroupAcl checks the user's own matching rules first. Group rules
// are only used when no user rule matches the topic, so a user rule can
// always narrow or deny what a group grants.
func CheckUserGroupAcl(user, group map[string]auth.Access, write bool) bool {
	if len(user) > 0 {
		return CheckAcl(user, write)
	}
	return CheckAcl(group, write)
}

// GroupTable describes the optional group ACL tables of a sql backend.
// Group ACLs are disabled unless both MemberTable and AclTable are set.
type GroupTable struct {
	MemberTable    string `json:"member-table" yaml:"member-table"`         // table mapping users to groups
	UserColumn     string `json:"user-column" yaml:"user-column"`           // user (or client id) column of MemberTable
	GroupColumn    string `json:"group-column" yaml:"group-column"`         // group column of MemberTable
	AclTable       string `json:"acl-table" yaml:"acl-table"`               // table of group topic rules
	AclGroupColumn string `json:"acl-group-column" yaml:"acl-group-column"` // group column of AclTable
	TopicColumn    string `json:"topic-column" yaml:"topic-column"`         // topic column of AclTable
	AccessColumn   string `json:"access-column" yaml:"access-column"`       // access column of AclTable
}

// Enabled returns true if group ACLs are configured.
func (g GroupTable) Enabled() bool {
	return g.MemberTable != "" && g.AclTable != ""
}

// AclSql returns the query selecting (topic, access) of all groups of a user,
// using placeholder for the user parameter (eg. "?" or "$1").
func (g GroupTable) AclSql(placeholder string) string {
	if g.UserColumn == "" {
		g.UserColumn = "username"
	}
	if g.GroupColumn == "" {
		g.GroupColumn = "groupname"
	}
	if g.AclGroupColumn == "" {
		g.AclGroupColumn = g.GroupColumn
	}
	if g.TopicColumn == "" {
		g.TopicColumn = "topic"
	}
	if g.AccessColumn == "" {
		g.AccessColumn = "access"
	}
	return fmt.Sprintf("select a.%s, a.%s from %s a join %s m on a.%s = m.%s where m.%s=%s",
		g.TopicColumn, g.AccessColumn, g.AclTable, g.MemberTable,
		g.AclGroupColumn, g.GroupColumn, g.UserColumn, placeholder)
}
