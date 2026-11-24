from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

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
        email = self.cleaned_data["username"].lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email. Sign in to continue.")
        return email

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
