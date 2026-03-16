from django.contrib import admin
from django import forms
from .models import MqttUser, MqttAcl

class MqttUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text="Leave empty to keep existing password")

    class Meta:
        model = MqttUser
        fields = '__all__'

    def save(self, commit=True):
        user = super().save(commit=False)
        raw_password = self.cleaned_data.get('password')
        if raw_password:
            user.set_password(raw_password)
        if commit:
            user.save()
        return user

@admin.register(MqttUser)
class MqttUserAdmin(admin.ModelAdmin):
    form = MqttUserForm
    list_display = ('username', 'is_superuser', 'created_at')
    search_fields = ('username',)

@admin.register(MqttAcl)
class MqttAclAdmin(admin.ModelAdmin):
    list_display = ('user', 'topic', 'access')
    list_filter = ('access', 'user')
    search_fields = ('topic', 'user__username')
