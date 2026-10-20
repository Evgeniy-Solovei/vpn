import re
from django import forms
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from .models import CustomUser

class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••••••',
            'class': 'form-input',
            'id': 'id_password'
        }),
        label="Мой секретный пароль"
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••••••',
            'class': 'form-input',
            'id': 'id_password_confirm'
        }),
        label="Повторите пароль"
    )

    class Meta:
        model = CustomUser
        fields = ['username', 'email']
        widgets = {
            'username': forms.TextInput(attrs={
                'placeholder': 'login',
                'class': 'form-input',
                'autocomplete': 'username',
                'id': 'id_username'
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'user@example.com',
                'class': 'form-input',
                'autocomplete': 'email',
                'id': 'id_email'
            }),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            raise ValidationError("Логин может содержать только латинские буквы и цифры")
        if CustomUser.objects.filter(username__iexact=username).exists():
            raise ValidationError("Пользователь с таким логином уже существует")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            # Special code for UI detection
            raise ValidationError("Этот email уже зарегистрирован", code='email_exists')
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password_confirm')
        if p1 and p2 and p1 != p2:
            self.add_error('password_confirm', "Пароли не совпадают")
        if p1:
            from django.contrib.auth.password_validation import validate_password
            try:
                validate_password(p1, self.instance)
            except ValidationError as err:
                self.add_error('password', err)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    login = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Логин или Email',
            'class': 'form-input',
            'autocomplete': 'username'
        }),
        label="Логин или Email"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••••••',
            'class': 'form-input',
            'autocomplete': 'current-password'
        }),
        label="Пароль"
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        label="Запомнить меня на 90 дней"
    )

    def clean(self):
        cleaned_data = super().clean()
        login_val = cleaned_data.get('login', '').strip()
        password = cleaned_data.get('password')

        if login_val and password:
            # Check if login is email or username
            user_obj = None
            if '@' in login_val:
                try:
                    user_obj = CustomUser.objects.get(email__iexact=login_val)
                except CustomUser.DoesNotExist:
                    pass
            else:
                try:
                    user_obj = CustomUser.objects.get(username__iexact=login_val)
                except CustomUser.DoesNotExist:
                    pass

            if user_obj:
                user = authenticate(username=user_obj.username, password=password)
                if user is not None:
                    cleaned_data['user'] = user
                    return cleaned_data
            raise ValidationError("Неверный логин или пароль")
        return cleaned_data


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'placeholder': 'Ваш email',
            'class': 'form-input',
            'autocomplete': 'email'
        }),
        label="Email"
    )


class SetNewPasswordForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Новый пароль',
            'class': 'form-input'
        }),
        label="Новый пароль"
    )
    new_password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Повторите новый пароль',
            'class': 'form-input'
        }),
        label="Повторите пароль"
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password')
        p2 = cleaned_data.get('new_password_confirm')
        if p1 and p2 and p1 != p2:
            self.add_error('new_password_confirm', "Пароли не совпадают")
        if p1 and len(p1) < 6:
            self.add_error('new_password', "Пароль должен быть не менее 6 символов")
        return cleaned_data
