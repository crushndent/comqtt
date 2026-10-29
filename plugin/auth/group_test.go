package auth

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/wind-c/comqtt/v2/mqtt/hooks/auth"
)

func TestMergeAccess(t *testing.T) {
	fam := make(map[string]auth.Access)
	MergeAccess(fam, "a/b", auth.ReadOnly)
	MergeAccess(fam, "a/b", auth.WriteOnly)
	MergeAccess(fam, "a/c", auth.Deny)
	require.Equal(t, auth.ReadWrite, fam["a/b"])
	require.Equal(t, auth.Deny, fam["a/c"])
}

func TestCheckUserGroupAcl(t *testing.T) {
	group := map[string]auth.Access{"a/#": auth.ReadWrite}
	// no user rule, group decides
	require.True(t, CheckUserGroupAcl(map[string]auth.Access{}, group, true))
	// a user rule narrows the group grant
	require.False(t, CheckUserGroupAcl(map[string]auth.Access{"a/b": auth.ReadOnly}, group, true))
	require.True(t, CheckUserGroupAcl(map[string]auth.Access{"a/b": auth.ReadOnly}, group, false))
	// a user rule denies despite the group grant
	require.False(t, CheckUserGroupAcl(map[string]auth.Access{"a/b": auth.Deny}, group, false))
	require.False(t, CheckUserGroupAcl(nil, nil, false))
}

func TestGroupTableEnabled(t *testing.T) {
	require.False(t, GroupTable{}.Enabled())
	require.False(t, GroupTable{MemberTable: "user_group"}.Enabled())
	require.True(t, GroupTable{MemberTable: "user_group", AclTable: "group_acl"}.Enabled())
}

func TestGroupTableAclSql(t *testing.T) {
	g := GroupTable{MemberTable: "user_group", AclTable: "group_acl"}
	require.Equal(t, "select a.topic, a.access from group_acl a join user_group m on a.groupname = m.groupname where m.username=?", g.AclSql("?"))

	g = GroupTable{
		MemberTable:    "members",
		UserColumn:     "client_id",
		GroupColumn:    "role",
		AclTable:       "role_acl",
		AclGroupColumn: "role_name",
		TopicColumn:    "filter",
		AccessColumn:   "perm",
	}
	require.Equal(t, "select a.filter, a.perm from role_acl a join members m on a.role_name = m.role where m.client_id=$1", g.AclSql("$1"))
}
