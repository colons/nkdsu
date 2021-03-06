import codecs
import datetime
from copy import copy
from os import path
from typing import Optional, Type

from django.conf import settings
from django.db.models import Model
from django.db.utils import NotSupportedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView
from markdown import markdown

from .models import Show, TwitterUser
from .utils import memoize


class CurrentShowMixin:
    def get_context_data(self):
        context = super(CurrentShowMixin, self).get_context_data()
        context['show'] = Show.current()
        return context


class LetMemoizeGetObject:
    def get_object(self, qs=None):
        if qs is None:
            return self._get_object()
        else:
            return super().get_object(qs=qs)


class ShowDetailMixin(LetMemoizeGetObject):
    """
    A view that will find a show for any date in the past, redirect to the
    showtime date if necessary, and then render a view with the correct show
    in context.
    """

    model: Optional[Type[Model]] = Show
    view_name: Optional[str] = None
    default_to_current = False

    @memoize
    def _get_object(self):
        """
        Get the show relating to self.date or, if self.date is None, the most
        recent complete show. If self.default_to_current is True, get the show
        in progress rather than the most recent complete show.

        Doesn't use Show.at() because I don't want views creating Shows in the
        database.
        """

        if self.date is None:
            qs = self.model.objects.all()

            if not self.default_to_current:
                qs = qs.filter(end__lt=timezone.now())

            qs = qs.order_by('-end')
        else:
            qs = self.model.objects.filter(showtime__gt=self.date)
            qs = qs.order_by('showtime')

        try:
            return qs[0]
        except IndexError:
            raise Http404

    def get(self, request, *args, **kwargs):
        date_fmt = '%Y-%m-%d'
        date_str = kwargs.get('date')

        fell_back = False

        if date_str is None:
            self.date = None
        else:
            try:
                naive_date = datetime.datetime.strptime(kwargs['date'],
                                                        date_fmt)
            except ValueError:
                try:
                    naive_date = datetime.datetime.strptime(kwargs['date'],
                                                            '%d-%m-%Y')
                except ValueError:
                    raise Http404
                else:
                    fell_back = True

            self.date = timezone.make_aware(naive_date,
                                            timezone.get_current_timezone())

        self.object = self.get_object()

        if (
            not fell_back and
            self.date is not None and
            self.object.showtime.date() == self.date.date()
        ):
            return super(ShowDetailMixin, self).get(request, *args, **kwargs)
        else:
            new_kwargs = copy(kwargs)
            name = (self.view_name or
                    ':'.join([request.resolver_match.namespace,
                              request.resolver_match.url_name]))
            new_kwargs['date'] = self.object.showtime.date().strftime(date_fmt)
            url = reverse(name, kwargs=new_kwargs)
            return redirect(url)

    def get_context_data(self, *args, **kwargs):
        context = super(ShowDetailMixin, self).get_context_data(*args,
                                                                **kwargs)

        context['show'] = self.get_object()
        return context


class ThisShowDetailMixin(ShowDetailMixin):
    """
    Like ShowDetailMixin, but defaults to the show in progress when no date is
    provided.
    """

    @memoize
    def get_object(self):
        if self.date is None:
            try:
                return self.model.at(timezone.now())
            except self.model.DoesNotExist:
                raise Http404
        else:
            return super(ThisShowDetailMixin, self).get_object()


class ShowDetail(ShowDetailMixin, DetailView):
    model: Type[Model] = Show


class ArchiveList(ListView):
    model: Optional[Type[Model]] = Show
    exclude_current = True

    def year(self):
        year = int(
            self.kwargs.get('year') or
            self.get_queryset().latest('showtime').showtime.year
        )

        if year not in self.get_years():
            raise Http404("We don't have shows for that year")

        return year

    def get_years(self):
        try:
            return list(
                self.get_queryset().order_by('showtime__year').distinct(
                    'showtime__year').values_list('showtime__year', flat=True)
            )
        except NotSupportedError:
            # we're probably running on sqlite
            return sorted(set(self.get_queryset().order_by('showtime__year')
                              .values_list('showtime__year', flat=True)))

    def get_queryset(self):
        qs = super().get_queryset().order_by('-showtime')

        if self.exclude_current:
            qs = qs.exclude(pk=self.model.current().pk)

        return qs

    def get_context_data(self):
        return {
            **super().get_context_data(),
            'years': self.get_years(),
            'year': self.year(),
            'object_list': self.get_queryset().filter(
                showtime__year=self.year()
            ),
        }


class MarkdownView(TemplateView):
    template_name = 'markdown.html'

    def get_context_data(self):
        context = super(MarkdownView, self).get_context_data()

        words = markdown(codecs.open(
            path.join(settings.PROJECT_ROOT, self.filename),
            encoding='utf-8'
        ).read())

        context.update({
            'title': self.title,
            'words': words,
        })

        return context


class TwitterUserDetailMixin(LetMemoizeGetObject):
    model: Type[Model] = TwitterUser

    @memoize
    def _get_object(self):
        user_id = self.kwargs.get('user_id')

        if user_id:
            return get_object_or_404(
                self.model, user_id=self.kwargs['user_id'],
            )

        users = self.model.objects.filter(
            screen_name__iexact=self.kwargs['screen_name'])

        if not users.exists():
            raise Http404
        elif users.count() == 1:
            user = users[0]
        else:
            user = users.order_by('-updated')[0]

        if user.vote_set.exists():
            return user
        else:
            raise Http404


class BreadcrumbMixin:
    def get_context_data(self, *a, **k):
        return {
            **super().get_context_data(*a, **k),
            'breadcrumbs': self.get_breadcrumbs(),
        }
