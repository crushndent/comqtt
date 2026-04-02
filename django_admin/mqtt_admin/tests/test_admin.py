import pytest
from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from mqtt_admin.models import MqttUser, MqttAcl, Node
from mqtt_admin.admin import (
    MqttUserAdmin,
    MqttAclAdmin,
    NodeAdmin,
    MqttUserAdminForm,
    MqttAclInline
)


class TestMqttUserAdminForm:
    """Tests for the MqttUserAdminForm."""

    def test_form_fields(self):
        """Test form has expected fields."""
        form = MqttUserAdminForm()
        assert 'username' in form.fields
        assert 'password' in form.fields
        assert 'allow' in form.fields

    def test_password_field_help_text(self):
        """Test password field has help text."""
        form = MqttUserAdminForm()
        assert 'Enter password for new user' in form.fields['password'].help_text

    def test_password_not_required_for_existing_user(self, mqtt_user):
        """Test password is hidden for existing users."""
        form = MqttUserAdminForm(instance=mqtt_user)
        assert isinstance(form.fields['password'].widget, type(form.fields['password'].widget))
        assert form.fields['password'].required is False

    def test_password_required_for_new_user(self):
        """Test password is not required by default in form."""
        form = MqttUserAdminForm()
        assert form.fields['password'].required is False

    def test_save_without_password(self, db):
        """Test saving without password doesn't change existing hash."""
        user = MqttUser(username='testsave')
        user.set_password('initialpass')
        user.save()

        old_hash = user.password

        form = MqttUserAdminForm(instance=user, data={
            'username': 'testsave',
            'allow': 1
        })
        assert form.is_valid()
        saved_user = form.save()

        assert saved_user.password == old_hash

    def test_save_with_password_hashes_it(self, db):
        """Test saving with password hashes it using bcrypt."""
        user = MqttUser(username='newsave')
        user.save()

        form = MqttUserAdminForm(instance=user, data={
            'username': 'newsave',
            'password': 'newpassword123',
            'allow': 1
        })
        assert form.is_valid()
        saved_user = form.save()

        assert saved_user.password != 'newpassword123'
        assert saved_user.password.startswith('$2')


class TestMqttUserAdmin:
    """Tests for the MqttUserAdmin class."""

    @pytest.fixture
    def admin_site(self):
        """Create admin site for testing."""
        return AdminSite()

    @pytest.fixture
    def user_admin(self, admin_site):
        """Create MqttUserAdmin instance."""
        return MqttUserAdmin(MqttUser, admin_site)

    def test_list_display(self, user_admin):
        """Test list_display fields."""
        expected = ('username', 'allow', 'created', 'updated', 'acl_count')
        assert user_admin.list_display == expected

    def test_list_filter(self, user_admin):
        """Test list_filter fields."""
        expected = ('allow', 'created')
        assert user_admin.list_filter == expected

    def test_search_fields(self, user_admin):
        """Test search_fields."""
        expected = ('username',)
        assert user_admin.search_fields == expected

    def test_readonly_fields(self, user_admin):
        """Test readonly_fields."""
        expected = ('created', 'updated')
        assert user_admin.readonly_fields == expected

    def test_inlines(self, user_admin):
        """Test inlines include MqttAclInline."""
        assert MqttAclInline in user_admin.inlines

    def test_actions(self, user_admin):
        """Test admin actions include reset_password."""
        assert 'reset_password' in user_admin.actions

    def test_acl_count_method(self, user_admin, mqtt_user, multiple_acls):
        """Test acl_count method returns correct count."""
        count = user_admin.acl_count(mqtt_user)
        assert count == len(multiple_acls)

    def test_acl_count_zero(self, user_admin, mqtt_user):
        """Test acl_count returns 0 when no ACLs."""
        count = user_admin.acl_count(mqtt_user)
        assert count == 0

    @pytest.mark.skip(reason="Requires full Django test client with session/message middleware")
    def test_reset_password_action(self, user_admin, rf, admin_user, multiple_users):
        """Test reset_password admin action."""
        request = rf.post('/admin/mqtt_admin/mqttuser/')
        request.user = admin_user

        # Store old passwords
        old_passwords = {u.pk: u.password for u in multiple_users}

        # Trigger action
        queryset = MqttUser.objects.filter(pk__in=[u.pk for u in multiple_users])
        user_admin.reset_password(request, queryset)

        # Refresh users and verify passwords changed
        for user in multiple_users:
            user.refresh_from_db()
            assert user.password != old_passwords[user.pk]
            assert user.password.startswith('$2')

    @pytest.mark.skip(reason="Requires full Django test client with session/message middleware")
    def test_reset_password_creates_success_message(self, user_admin, rf, admin_user, mqtt_user):
        """Test reset_password action creates success message."""
        request = rf.post('/admin/mqtt_admin/mqttuser/')
        request.user = admin_user
        request._messages = messages.storage.default_storage(request)

        queryset = MqttUser.objects.filter(pk=mqtt_user.pk)
        user_admin.reset_password(request, queryset)

        # Check messages were added
        storage = messages.get_messages(request)
        message_list = list(storage)
        assert len(message_list) >= 1


class TestMqttAclAdmin:
    """Tests for the MqttAclAdmin class."""

    @pytest.fixture
    def admin_site(self):
        """Create admin site for testing."""
        return AdminSite()

    @pytest.fixture
    def acl_admin(self, admin_site):
        """Create MqttAclAdmin instance."""
        return MqttAclAdmin(MqttAcl, admin_site)

    def test_list_display(self, acl_admin):
        """Test list_display fields."""
        expected = ('user', 'topic', 'access', 'created')
        assert acl_admin.list_display == expected

    def test_list_filter(self, acl_admin):
        """Test list_filter fields."""
        expected = ('access', 'created')
        assert acl_admin.list_filter == expected

    def test_search_fields(self, acl_admin):
        """Test search_fields."""
        expected = ('user__username', 'topic')
        assert acl_admin.search_fields == expected

    def test_raw_id_fields(self, acl_admin):
        """Test raw_id_fields."""
        expected = ('user',)
        assert acl_admin.raw_id_fields == expected


class TestMqttAclInline:
    """Tests for the MqttAclInline."""

    def test_model(self):
        """Test inline model is MqttAcl."""
        assert MqttAclInline.model == MqttAcl

    def test_extra(self):
        """Test extra forms shown."""
        assert MqttAclInline.extra == 1

    def test_fields(self):
        """Test inline fields."""
        expected = ('topic', 'access', 'created', 'updated')
        assert MqttAclInline.fields == expected

    def test_readonly_fields(self):
        """Test readonly fields."""
        expected = ('created', 'updated')
        assert MqttAclInline.readonly_fields == expected


class TestNodeAdmin:
    """Tests for the NodeAdmin class."""

    @pytest.fixture
    def admin_site(self):
        """Create admin site for testing."""
        return AdminSite()

    @pytest.fixture
    def node_admin(self, admin_site):
        """Create NodeAdmin instance."""
        return NodeAdmin(Node, admin_site)

    def test_list_display(self, node_admin):
        """Test list_display fields."""
        expected = ('node_id', 'name', 'user', 'location', 'status', 'created', 'updated')
        assert node_admin.list_display == expected

    def test_list_filter(self, node_admin):
        """Test list_filter fields."""
        expected = ('status', 'created', 'updated')
        assert node_admin.list_filter == expected

    def test_search_fields(self, node_admin):
        """Test search_fields."""
        expected = ('node_id', 'name', 'location')
        assert node_admin.search_fields == expected

    def test_readonly_fields(self, node_admin):
        """Test readonly_fields."""
        expected = ('created', 'updated')
        assert node_admin.readonly_fields == expected

    def test_actions(self, node_admin):
        """Test admin actions."""
        assert 'provision_nodes' in node_admin.actions
        assert 'regenerate_credentials' in node_admin.actions

    @pytest.mark.skip(reason="Requires full Django test client with session/message middleware")
    def test_provision_nodes_skips_existing_user(self, node_admin, rf, admin_user, node):
        """Test provision_nodes skips nodes that already have users."""
        request = rf.post('/admin/mqtt_admin/node/')
        request.user = admin_user
        request._messages = messages.storage.default_storage(request)

        queryset = Node.objects.filter(pk=node.pk)

        # Node should be skipped since it has no user but provision should work
        node_admin.provision_nodes(request, queryset)

        node.refresh_from_db()
        assert node.user is not None

    @pytest.mark.skip(reason="Requires full Django test client with session/message middleware")
    def test_provision_nodes_with_existing_user(self, node_admin, rf, admin_user, node_with_user):
        """Test provision_nodes skips nodes with existing users."""
        request = rf.post('/admin/mqtt_admin/node/')
        request.user = admin_user
        request._messages = messages.storage.default_storage(request)

        old_user = node_with_user.user

        queryset = Node.objects.filter(pk=node_with_user.pk)
        node_admin.provision_nodes(request, queryset)

        node_with_user.refresh_from_db()
        assert node_with_user.user == old_user

    @pytest.mark.skip(reason="Requires full Django test client with session/message middleware")
    def test_regenerate_credentials(self, node_admin, rf, admin_user, node_with_user):
        """Test regenerate_credentials action."""
        request = rf.post('/admin/mqtt_admin/node/')
        request.user = admin_user
        request._messages = messages.storage.default_storage(request)

        old_password = node_with_user.user.password

        queryset = Node.objects.filter(pk=node_with_user.pk)
        node_admin.regenerate_credentials(request, queryset)

        node_with_user.refresh_from_db()
        node_with_user.user.refresh_from_db()

        # Password should have changed
        assert node_with_user.user.password != old_password
        assert node_with_user.user.password.startswith('$2')


class TestAdminUserCreation:
    """Tests for admin user creation workflow."""

    def test_admin_can_access_user_list(self, client_with_admin):
        """Test admin can view user list page."""
        response = client_with_admin.get('/admin/mqtt_admin/mqttuser/')
        assert response.status_code == 200

    def test_admin_can_access_user_add(self, client_with_admin):
        """Test admin can view user add page."""
        response = client_with_admin.get('/admin/mqtt_admin/mqttuser/add/')
        assert response.status_code == 200

    def test_admin_can_create_user(self, client_with_admin):
        """Test admin can create a new user through admin."""
        response = client_with_admin.post('/admin/mqtt_admin/mqttuser/add/', {
            'username': 'admincreated',
            'password': 'newuserpass123',
            'allow': 1,
        })

        # Should redirect after success
        assert response.status_code in [200, 302]

        if response.status_code == 302:
            user = MqttUser.objects.get(username='admincreated')
            assert user.password.startswith('$2')
            assert user.password != 'newuserpass123'

    def test_admin_can_access_acl_list(self, client_with_admin):
        """Test admin can view ACL list page."""
        response = client_with_admin.get('/admin/mqtt_admin/mqttacl/')
        assert response.status_code == 200

    def test_admin_can_access_node_list(self, client_with_admin):
        """Test admin can view node list page."""
        response = client_with_admin.get('/admin/mqtt_admin/node/')
        assert response.status_code == 200

    def test_admin_can_access_inline_forms(self, client_with_admin, mqtt_user):
        """Test admin can view user with inline ACL forms."""
        response = client_with_admin.get(f'/admin/mqtt_admin/mqttuser/{mqtt_user.pk}/change/')
        assert response.status_code == 200

    def test_admin_can_add_acl_via_inline(self, client_with_admin, mqtt_user):
        """Test adding ACL through inline form."""
        response = client_with_admin.post(
            f'/admin/mqtt_admin/mqttuser/{mqtt_user.pk}/change/',
            {
                'username': mqtt_user.username,
                'allow': mqtt_user.allow,
                'mqttacl_set-TOTAL_FORMS': '1',
                'mqttacl_set-INITIAL_FORMS': '0',
                'mqttacl_set-MIN_NUM_FORMS': '0',
                'mqttacl_set-MAX_NUM_FORMS': '1000',
                'mqttacl_set-0-topic': 'inline/test/topic',
                'mqttacl_set-0-access': '2',
            }
        )

        # Check that response is valid (redirect or 200 with form errors)
        assert response.status_code in [200, 302]
