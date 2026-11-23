from django import forms

from .catalogue import PROGRAMS


PROGRAM_CHOICES = [
    (program["id"], f'{program["title"]} · {program["short"]}')
    for program in PROGRAMS
] + [("help", "Help choosing a class"), ("general", "Something else")]

PROGRAM_AGES = {
    program["id"]: tuple(card["age"] for card in program["cards"])
    for program in PROGRAMS
}


class EnquiryForm(forms.Form):
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
        error_messages={"required": "Enter your email address."},
    )
    program = forms.ChoiceField(choices=[("", "Choose a topic"), *PROGRAM_CHOICES])
    age = forms.CharField(required=False, max_length=12)
    message = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 4}))

    def clean(self):
        cleaned = super().clean()
        age = cleaned.get("age")
        if age and age not in PROGRAM_AGES.get(cleaned.get("program"), ()):
            self.add_error("age", "Choose an age group for the selected class.")
        return cleaned
