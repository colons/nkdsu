import re

import tweepy

from django import forms
from django.core.validators import validate_email
from django.conf import settings
from django.utils.safestring import mark_safe

from .models import Vote, Request
from ..vote import trivia


post_tw_auth = tweepy.OAuthHandler(settings.CONSUMER_KEY,
                                   settings.CONSUMER_SECRET)
post_tw_auth.set_access_token(settings.POSTING_ACCESS_TOKEN,
                              settings.POSTING_ACCESS_TOKEN_SECRET)
tw_api = tweepy.API(post_tw_auth)


def email_or_twitter(address):
    try:
        validate_email(address)
    except forms.ValidationError:
        try:
            tw_api.get_user(screen_name=address.lstrip('@'))
        except tweepy.TweepError:
            raise forms.ValidationError(
                'Enter a valid email address or twitter username')


class EmailOrTwitterField(forms.EmailField):
    default_error_messages = {
        'invalid': u'Enter a valid email address or Twitter username',
    }
    default_validators = [email_or_twitter]


class SearchForm(forms.Form):
    q = forms.CharField()


class TriviaForm(forms.Form):
    """
    A form protected by a trivia question.
    """

    trivia_question = forms.CharField(widget=forms.HiddenInput)
    trivia = forms.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super(TriviaForm, self).__init__(*args, **kwargs)
        self.fields.keyOrder.append(self.fields.keyOrder.pop(1))

    def clean_trivia(self):
        human = True

        if 'trivia' in self.cleaned_data:
            human = re.match(
                trivia.questions[self.cleaned_data['trivia_question']] + '$',
                self.cleaned_data['trivia'], re.I)

        request = Request()
        request.successful = bool(human)
        request.serialise(self.cleaned_data)
        request.save()

        if not human:
            hint = (
                "That's not right, sorry. There are hints <a href='https://"
                "github.com/colons/nkdsu/blob/master/vote/trivia.py'>here</a>."
            )

            raise forms.ValidationError([mark_safe(hint)])

        return self.cleaned_data['trivia']


class BadMetadataForm(TriviaForm):
    details = forms.CharField(widget=forms.Textarea,
                              label="What needs fixing?", required=False)
    contact = EmailOrTwitterField(label="Email/Twitter (not required)",
                                  required=False)


class RequestForm(TriviaForm):
    title = forms.CharField(required=False)
    artist = forms.CharField(required=False)
    show = forms.CharField(label="Source Anime", required=False)
    role = forms.CharField(label="Role (OP/ED/Insert/Character/etc.)",
                           required=False)
    details = forms.CharField(widget=forms.Textarea,
                              label="Additional Details", required=False)
    contact = EmailOrTwitterField(label="Email Address/Twitter name",
                                  required=True)

    def clean(self):
        cleaned_data = super(RequestForm, self).clean()

        compulsory = ['trivia', 'trivia_question', 'contact']

        filled = [cleaned_data[f] for f in cleaned_data
                  if f not in compulsory and cleaned_data[f]]

        if len(filled) < 2:
            raise forms.ValidationError(
                "I'm sure you can give us more information than that.")

        return cleaned_data


class LibraryUploadForm(forms.Form):
    library_xml = forms.FileField(label='Library XML')
    inudesu = forms.BooleanField(label='Inu Desu', required=False)


class ManualVoteForm(forms.ModelForm):
    """ Make a manual vote! """

    class Meta:
        # XXX pick safe things
        model = Vote


class BlockForm(forms.Form):
    """ Block something """
    reason = forms.CharField(max_length=256)