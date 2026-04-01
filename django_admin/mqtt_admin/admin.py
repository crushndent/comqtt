from django.contrib import admin
from django import forms
from django.contrib import messages
from django.utils.translation import ngettext

from .models import MqttUser, MqttAcl, Node
from .node_provisioning import provision_node, regenerate_node_credentials


class MqttAclInline(admin.StackedInline):
    model = MqttAcl
    extra = 1
    fields = ('username', 'topic', 'access', 'created', 'updated')
    readonly_fields = ('created', 'updated')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj:
            formset.form.base_fields['username'].initial = obj.username
        return formset


class MqttUserAdminForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Enter password'}),
        required=False,
        help_text='Enter password for new user. Leave blank when editing to keep existing password.'
    )

    class Meta:
        model = MqttUser
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['password'].widget = forms.HiddenInput()
            self.fields['password'].required = False

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


@admin.register(MqttUser)
class MqttUserAdmin(admin.ModelAdmin):
    form = MqttUserAdminForm
    list_display = ('username', 'allow', 'created', 'updated', 'acl_count')
    list_filter = ('allow', 'created')
    search_fields = ('username',)
    readonly_fields = ('created', 'updated')
    inlines = [MqttAclInline]
    actions = ['reset_password']

    def acl_count(self, obj):
        return MqttAcl.objects.filter(username=obj.username).count()
    acl_count.short_description = 'ACL Count'

    @admin.action(description='Reset password for selected users')
    def reset_password(self, request, queryset):
        updated = 0
        for user in queryset:
            temp_password = MqttUser.objects.make_random_password(length=12)
            user.set_password(temp_password)
            user.save()
            self.message_user(
                request,
                f'Password reset for user "{user.username}". Temporary password: {temp_password}',
                messages.SUCCESS
            )
            updated += 1
        self.message_user(
            request,
            ngettext(
                '%d user was reset.',
                '%d users were reset.',
                updated,
            ) % updated,
            messages.SUCCESS,
        )


@admin.register(MqttAcl)
class MqttAclAdmin(admin.ModelAdmin):
    list_display = ('username', 'topic', 'access', 'created')
    list_filter = ('access', 'created')
    search_fields = ('username', 'topic')


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('node_id', 'name', 'user', 'location', 'status', 'created', 'updated')
    list_filter = ('status', 'created', 'updated')
    search_fields = ('node_id', 'name', 'location')
    readonly_fields = ('created', 'updated')
    actions = ['provision_nodes', 'regenerate_credentials']

    @admin.action(description='Provision selected nodes')
    def provision_nodes(self, request, queryset):
        """Create MQTT user and ACLs for selected nodes."""
        provisioned = 0
        failed = 0

        for node in queryset:
            if node.user:
                self.message_user(
                    request,
                    f'Node "{node.node_id}" already has a user. Skipping.',
                    messages.WARNING
                )
                failed += 1
                continue

            try:
                user = provision_node(node.node_id, node.name)
                node.user = user
                node.status = 'active'
                node.save()

                self.message_user(
                    request,
                    f'Successfully provisioned node "{node.node_id}". '
                    f'Username: {user.username}, Password: {user._plain_password}',
                    messages.SUCCESS
                )
                provisioned += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Failed to provision node "{node.node_id}": {str(e)}',
                    messages.ERROR
                )
                failed += 1

        if provisioned > 0:
            self.message_user(
                request,
                ngettext(
                    '%d node was provisioned.',
                    '%d nodes were provisioned.',
                    provisioned,
                ) % provisioned,
                messages.SUCCESS,
            )

    @admin.action(description='Regenerate credentials for selected nodes')
    def regenerate_credentials(self, request, queryset):
        """Reset password and update ACLs for selected nodes."""
        updated = 0
        failed = 0

        for node in queryset:
            try:
                user = regenerate_node_credentials(node)
                node.user = user
                node.save()

                self.message_user(
                    request,
                    f'Successfully regenerated credentials for "{node.node_id}". '
                    f'New password: {user._plain_password}',
                    messages.SUCCESS
                )
                updated += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Failed to regenerate credentials for "{node.node_id}": {str(e)}',
                    messages.ERROR
                )
                failed += 1

        if updated > 0:
            self.message_user(
                request,
                ngettext(
                    '%d node credential was regenerated.',
                    '%d node credentials were regenerated.',
                    updated,
                ) % updated,
                messages.SUCCESS,
            )
