# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import base64
import six
import urlparse
import vobject
import warnings

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
try:
    from django.utils.encoding import force_unicode
except ImportError:
    from django.utils.encoding import force_text as force_unicode
from django.utils.text import slugify as django_slugify
from django.utils.translation import ugettext_lazy as _, ugettext, override

from aldryn_common.admin_fields.sortedm2m import SortedM2MModelField
from cms.models.pluginmodel import CMSPlugin
from cms.utils.i18n import get_current_language, get_languages
from djangocms_text_ckeditor.fields import HTMLField
from filer.fields.image import FilerImageField
from parler.models import TranslatableModel, TranslatedFields
from sortedm2m.fields import SortedManyToManyField

from .utils import get_additional_styles

LANGUAGE_CODES = [l['code'] for l in get_languages()]


def slugify(source_text, i=None):
    slug = django_slugify(source_text)
    if i is not None:
        slug += "_%d" % i
    return slug


@python_2_unicode_compatible
class Group(TranslatableModel):
    translations = TranslatedFields(
        name=models.CharField(_('name'), max_length=255,
                              help_text=_("Provide this group's name.")),
        description=HTMLField(_('description'), blank=True),
        slug=models.SlugField(_('slug'), max_length=255, default='',
            blank=True,
            help_text=_("Leave blank to auto-generate a unique slug.")),
    )
    address = models.TextField(
        verbose_name=_('address'), blank=True)
    postal_code = models.CharField(
        verbose_name=_('postal code'), max_length=20, blank=True)
    city = models.CharField(
        verbose_name=_('city'), max_length=255, blank=True)
    phone = models.CharField(
        verbose_name=_('phone'), null=True, blank=True, max_length=100)
    fax = models.CharField(
        verbose_name=_('fax'), null=True, blank=True, max_length=100)
    email = models.EmailField(
        verbose_name=_('email'), blank=True, default='')
    website = models.URLField(
        verbose_name=_('website'), null=True, blank=True)

    @property
    def company_name(self):
        warnings.warn(
            '"Group.company_name" has been refactored to "Group.name"',
            DeprecationWarning
        )
        return self.safe_translation_getter('name')

    @property
    def company_description(self):
        warnings.warn(
            '"Group.company_description" has been refactored to '
            '"Group.description"',
            DeprecationWarning
        )
        return self.safe_translation_getter('description')

    class Meta:
        verbose_name = _('Group')
        verbose_name_plural = _('Groups')

    def __str__(self):
        return self.safe_translation_getter(
            'name', default=_('Group: {0}').format(self.pk))

    def get_absolute_url(self, language=None):
        if not language:
            language = get_current_language()
        slug = self.safe_translation_getter(
            'slug', None, language_code=language, any_language=False)
        if slug:
            kwargs = {'slug': slug}
        else:
            kwargs = {'pk': self.pk}
        with override(language):
            return reverse('aldryn_people:group-detail', kwargs=kwargs)

    def save(self, **kwargs):
        language = self.get_current_language()
        if not self.slug:
            self.slug = force_unicode(django_slugify(self.name))
        # If there is still no slug, we must give it something to start with
        if not self.slug:
            self.slug = ugettext('unnamed-group')
        if not Group.objects.language(language).filter(
                translations__slug=self.slug).exclude(pk=self.pk).exists():
            return super(Group, self).save(**kwargs)
        for lang in LANGUAGE_CODES:
            #
            # We'd much rather just do something like:
            # Group.objects.translated(lang, slug__startswith=self.slug)
            # But sadly, this isn't supported by Parler/Django, see:
            # http://django-parler.readthedocs.org/en/latest/api/\
            #     parler.managers.html#the-translatablequeryset-class
            #
            slugs = []
            all_slugs = (
                Group.objects.language(lang)
                             .exclude(pk=self.pk)
                             .values_list('translations__slug', flat=True)
            )
            for slug in all_slugs:
                if slug and slug.startswith((self.name, self.slug)):
                    slugs.append(slug)
            i = 1
            while True:
                slug = slugify(self.name or self.slug, i)
                if slug not in slugs:
                    self.slug = slug
                    return super(Group, self).save(**kwargs)
                i += 1


@python_2_unicode_compatible
class Person(TranslatableModel):
    translations = TranslatedFields(
        name=models.CharField(_('name'), max_length=255, blank=False,
            default='', help_text=_("Provide this person's name.")),
        slug=models.SlugField(_('unique slug'), max_length=255, blank=True,
            default='',
            help_text=_("Leave blank to auto-generate a unique slug.")),
        function=models.CharField(
            _('function'), max_length=255, blank=True, default=''),
        description=HTMLField(
            _('Description'), blank=True, default='')
    )
    phone = models.CharField(
        verbose_name=_('phone'), null=True, blank=True, max_length=100)
    mobile = models.CharField(
        verbose_name=_('mobile'), null=True, blank=True, max_length=100)
    fax = models.CharField(
        verbose_name=_('fax'), null=True, blank=True, max_length=100)
    email = models.EmailField(
        verbose_name=_("email"), blank=True, default='')
    website = models.URLField(
        verbose_name=_('website'), null=True, blank=True)
    groups = SortedManyToManyField(
        'aldryn_people.Group', default=None, blank=True, related_name='people',
        help_text=_('Choose and order the groups for this person, the first '
                    'will be the "primary group".'))
    visual = FilerImageField(
        null=True, blank=True, default=None, on_delete=models.SET_NULL)
    vcard_enabled = models.BooleanField(
        verbose_name=_('enable vCard download'), default=True)
    user = models.ForeignKey(
        getattr(settings, 'AUTH_USER_MODEL', 'auth.User'),
        null=True, blank=True, unique=True, related_name='persons')

    class Meta:
        verbose_name = _('Person')
        verbose_name_plural = _('People')
        # FIXME: ordering = ['name', ]

    def __str__(self):
        pkstr = str(self.pk)

        if six.PY2:
            pkstr = six.u(pkstr)
        name = self.name.strip()
        return name if len(name) > 0 else pkstr

    @property
    def primary_group(self):
        """Simply returns the first in `groups`, if any, else None."""
        return self.groups.first()

    @property
    def comment(self):
        return self.safe_translation_getter('description', '')

    def get_absolute_url(self, language=None):
        if not language:
            language = get_current_language()
        slug = self.safe_translation_getter(
            'slug', None, language_code=language, any_language=False)
        if slug:
            kwargs = {'slug': slug}
        else:
            kwargs = {'pk': self.pk}
        with override(language):
            return reverse('aldryn_people:person-detail', kwargs=kwargs)

    def get_vcard(self, request=None):
        if self.primary_group:
            group_name = self.primary_group.safe_translation_getter(
                'name', default="Group: {0}".format(self.primary_group.pk))
        else:
            group_name = ''
        function = self.safe_translation_getter('function')

        vcard = vobject.vCard()
        safe_name = self.safe_translation_getter(
            'name', default="Person: {0}".format(self.pk))
        vcard.add('n').value = vobject.vcard.Name(given=safe_name)
        vcard.add('fn').value = safe_name

        if self.visual:
            try:
                with open(self.visual.path, 'rb') as f:
                    photo = vcard.add('photo')
                    photo.type_param = self.visual.extension.upper()
                    photo.value = base64.b64encode(f.read())
                    photo.encoded = True
                    photo.encoding_param = 'B'
            except IOError:
                if request:
                    photo = vcard.add('photo')
                    photo.type_param = self.visual.extension.upper()
                    photo.value = urlparse.urljoin(
                        request.build_absolute_uri(), self.visual.url)

        if self.email:
            vcard.add('email').value = self.email
        if function:
            vcard.add('title').value = function
        if self.phone:
            tel = vcard.add('tel')
            tel.value = unicode(self.phone)
            tel.type_param = 'WORK'
        if self.mobile:
            tel = vcard.add('tel')
            tel.value = unicode(self.mobile)
            tel.type_param = 'CELL'
        if self.fax:
            fax = vcard.add('tel')
            fax.value = unicode(self.fax)
            fax.type_param = 'FAX'
        if self.website:
            website = vcard.add('url')
            website.value = unicode(self.website)

        if self.primary_group:
            if group_name:
                vcard.add('org').value = [group_name]
            if (self.primary_group.address or self.primary_group.city or
                    self.primary_group.postal_code):
                vcard.add('adr')
                vcard.adr.type_param = 'WORK'
                vcard.adr.value = vobject.vcard.Address()
                if self.primary_group.address:
                    vcard.adr.value.street = self.primary_group.address
                if self.primary_group.city:
                    vcard.adr.value.city = self.primary_group.city
                if self.primary_group.postal_code:
                    vcard.adr.value.code = self.primary_group.postal_code
            if self.primary_group.phone:
                tel = vcard.add('tel')
                tel.value = unicode(self.primary_group.phone)
                tel.type_param = 'WORK'
            if self.primary_group.fax:
                fax = vcard.add('tel')
                fax.value = unicode(self.primary_group.fax)
                fax.type_param = 'FAX'
            if self.primary_group.website:
                website = vcard.add('url')
                website.value = unicode(self.primary_group.website)

        return vcard.serialize()

    def save(self, **kwargs):
        language = self.get_current_language()
        if not self.slug:
            self.slug = force_unicode(django_slugify(self.name))
        # If there is still no slug, we must give it something to start with
        if not self.slug:
            self.slug = ugettext('unnamed-person')
        if not Person.objects.language(language).filter(
                translations__slug=self.slug).exclude(pk=self.pk).exists():
            return super(Person, self).save(**kwargs)
        for lang in LANGUAGE_CODES:
            #
            # We'd much rather just do something like:
            # Person.objects.translated(lang, slug__startswith=self.slug)
            # But sadly, this isn't supported by Parler/Django, see:
            # http://django-parler.readthedocs.org/en/latest/api/\
            #     parler.managers.html#the-translatablequeryset-class
            #
            slugs = []
            all_slugs = (
                Person.objects.language(lang)
                              .exclude(pk=self.pk)
                              .values_list('translations__slug', flat=True)
            )
            for slug in all_slugs:
                if slug and slug.startswith((self.name, self.slug)):
                    slugs.append(slug)
            i = 1
            while True:
                slug = slugify(self.name or self.slug, i)
                if slug not in slugs:
                    self.slug = slug
                    return super(Person, self).save(**kwargs)
                i += 1


@python_2_unicode_compatible
class BasePeoplePlugin(CMSPlugin):

    STYLE_CHOICES = [
        ('standard', _('Standard')),
        ('feature', _('Feature'))
    ] + get_additional_styles()

    style = models.CharField(
        _('Style'), choices=STYLE_CHOICES,
        default=STYLE_CHOICES[0][0], max_length=50)
    people = SortedM2MModelField(
        Person, blank=True, null=True)
    group_by_group = models.BooleanField(
        verbose_name=_('group by group'),
        default=True,
        help_text=_('when checked, people are grouped by their group')
    )
    show_links = models.BooleanField(
        verbose_name=_('Show links to Detail Page'), default=False)
    show_vcard = models.BooleanField(
        verbose_name=_('Show links to download vCard'), default=False)

    class Meta:
        abstract = True

    def __str__(self):
        return unicode(self.pk)

    def copy_relations(self, oldinstance):
        self.people = oldinstance.people.all()

    def get_selected_people(self):
        return self.people.select_related('group', 'visual')


class PeoplePlugin(BasePeoplePlugin):

    class Meta:
        abstract = False
