from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from .models import Student


User = get_user_model()


class FamilyRegistrationForm(UserCreationForm):
    username = forms.EmailField(
        label="Parent or carer email",
        max_length=150,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    first_name = forms.CharField(label="Parent or carer name", max_length=150)
    student_name = forms.CharField(label="Student name", max_length=100)

    field_order = ["first_name", "username", "student_name", "password1", "password2"]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["first_name", "username"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password2"].label = "Confirm password"
        self.fields["password2"].help_text = ""

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        # The view distinguishes active accounts from pending email verifications.
        self._validate_unique = False
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["username"]
        if commit:
            user.save()
        return user


class FamilyLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        max_length=150,
        widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}),
    )

    def clean_username(self):
        return self.cleaned_data["username"].lower()


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["name"]
        labels = {"name": "Student name"}


class SelectClassForm(forms.Form):
    student = forms.ModelChoiceField(label="Student", queryset=Student.objects.none(), empty_label="Choose a student")
    session = forms.ChoiceField(label="Dates and time")

    def __init__(self, *args, parent, sessions, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = parent.students.all()
        self.fields["session"].choices = sessions


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        max_length=150,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class VerificationCodeForm(forms.Form):
    code = forms.RegexField(
        regex=r"^\d{6}$",
        error_messages={"invalid": "Enter the six-digit code from your email."},
        widget=forms.TextInput(attrs={
            "autocomplete": "one-time-code",
            "inputmode": "numeric",
            "pattern": "[0-9]{6}",
            "maxlength": "6",
        }),
    )


class FamilyPasswordResetForm(VerificationCodeForm):
    password1 = forms.CharField(
        label="New password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm new password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        try:
            password_validation.validate_password(password, user=self.user)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        return password

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        return cleaned
