import logging
import os
import random
import re
import tempfile
import zipfile

from django.contrib.auth.models import Group, BaseUserManager, AbstractBaseUser
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Q
from django.db.models.query import QuerySet
from django.utils.text import slugify
from mptt.exceptions import InvalidMove
from mptt.models import MPTTModel, TreeForeignKey
import tempdir

from perma.utils import base

logger = logging.getLogger(__name__)


class Registrar(models.Model):
    """
    This is generally a library.
    """
    name = models.CharField(max_length=400)
    email = models.EmailField(max_length=254)
    website = models.URLField(max_length=500)
    default_vesting_org = models.OneToOneField('VestingOrg', blank=True, null=True, related_name='default_for_registrars')

    def save(self, *args, **kwargs):
        super(Registrar, self).save(*args, **kwargs)
        self.create_default_vesting_org()

    def __unicode__(self):
        return self.name

    def create_default_vesting_org(self):
        """
            Create a default vesting org for this registrar, if there isn't one.
            Before creating a new one, we check if registrar has only a single vesting org,
            or else one called "Default Vesting Organization",
            and if so use that one.

            NOTE: In theory registrars created from now on shouldn't need these checks, and they could be deleted.
        """
        if self.default_vesting_org:
            return
        vesting_orgs = list(self.vesting_orgs.all())
        if len(vesting_orgs) == 1:
            vesting_org = vesting_orgs[0]
        else:
            for candidate_vesting_org in vesting_orgs:
                if candidate_vesting_org.name == "Default Vesting Organization":
                    vesting_org = candidate_vesting_org
                    break
            else:
                vesting_org = VestingOrg(registrar=self, name="Default Vesting Organization")
                vesting_org.save()
        self.default_vesting_org = vesting_org
        self.save()

        
class VestingOrg(models.Model):
    """
    This is generally a journal.
    """
    name = models.CharField(max_length=400)
    registrar = models.ForeignKey(Registrar, null=True, related_name="vesting_orgs")
    shared_folder = models.OneToOneField('Folder', blank=True, null=True)

    def save(self, *args, **kwargs):
        """ Make sure shared folder is created for each vesting org. """
        super(VestingOrg, self).save(*args, **kwargs)
        if not self.shared_folder:
            self.create_shared_folder()

    def __unicode__(self):
        return self.name

    def create_shared_folder(self):
        if self.shared_folder:
            return
        print self.name
        shared_folder = Folder(name=self.name, vesting_org=self, is_shared_folder=True)
        shared_folder.save()
        self.shared_folder = shared_folder
        self.save()


class LinkUserManager(BaseUserManager):
    def create_user(self, email, registrar, vesting_org, date_joined, first_name, last_name, authorized_by, confirmation_code, password=None, groups=None):
        """
        Creates and saves a User with the given email, registrar and password.
        """
        if not email:
            raise ValueError('Users must have an email address')

        user = self.model(
            email=self.normalize_email(email),
            registrar=registrar,
            vesting_org=vesting_org,
            groups=groups,
            date_joined = date_joined,
            first_name = first_name,
            last_name = last_name,
            authorized_by = authorized_by,
            confirmation_code = confirmation_code
        )

        user.set_password(password)
        user.save()

        user.create_root_folder()

        return user


class LinkUser(AbstractBaseUser):
    email = models.EmailField(
        verbose_name='email address',
        max_length=255,
        unique=True,
        db_index=True,
    )
    registrar = models.ForeignKey(Registrar, null=True)
    vesting_org = models.ForeignKey(VestingOrg, null=True, related_name='users')
    groups = models.ManyToManyField(Group, null=True)
    is_active = models.BooleanField(default=True)
    is_confirmed = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    date_joined = models.DateField(auto_now_add=True)
    first_name = models.CharField(max_length=45, blank=True)
    last_name = models.CharField(max_length=45, blank=True)
    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='authorized_by_manager')
    confirmation_code = models.CharField(max_length=45, blank=True)
    root_folder = models.OneToOneField('Folder', blank=True, null=True)

    objects = LinkUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        """ Make sure root folder is created for each user. """
        super(LinkUser, self).save(*args, **kwargs)
        if not self.root_folder:
            self.create_root_folder()

    def get_full_name(self):
        """ Use either First Last or first half of email address as user's name. """
        return "%s %s" % (self.first_name, self.last_name) if self.first_name or self.last_name else \
            self.email.split('@')[0]

    def get_short_name(self):
        """ Use either First or Last or first half of email address as user's short name. """
        return self.first_name or self.last_name or self.email.split('@')[0]

    # On Python 3: def __str__(self):
    def __unicode__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        # Simplest possible answer: Yes, always
        return True

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin

    def has_group(self, group):
        """
            Return true if user is in the named group.
            If group is a list, user must be in one of the groups in the list.
        """
        if hasattr(group, '__iter__'):
            return self.groups.filter(name__in=group).exists()
        else:
            return self.groups.filter(name=group).exists()

    def all_folder_trees(self):
        """
            Get all folders for this user, including shared folders
        """
        if self.has_group('registrar_user'):
            vesting_orgs = self.registrar.vesting_orgs.all()
        else:
            vesting_orgs = [self.get_default_vesting_org()]
        return [self.root_folder.get_descendants(include_self=True)] + \
            ([vesting_org.shared_folder.get_descendants(include_self=True) for vesting_org in vesting_orgs if vesting_org])

    def get_default_vesting_org(self):
        if self.vesting_org:
            return self.vesting_org
        if self.registrar:
            return self.registrar.default_vesting_org
        if self.has_group('registry_user'):
            try:
                return VestingOrg.objects.get(pk=settings.FALLBACK_VESTING_ORG_ID)
            except VestingOrg.DoesNotExist:
                raise Exception("Default vesting org not found -- check FALLBACK_VESTING_ORG_ID setting.")
        return None

    def create_root_folder(self):
        if self.root_folder:
            return
        try:
            # this branch only used during transition to root folders -- should be removed eventually
            root_folder = Folder.objects.filter(created_by=self, name=u"My Links", parent=None)[0]
        except IndexError:
            root_folder = Folder(name=u'My Links', created_by=self, is_root_folder=True)
            root_folder.save()
        self.root_folder = root_folder
        self.save()


class FolderException(Exception):
    pass


class FolderQuerySet(QuerySet):
    def accessible_to(self, user):
        return self.filter(Folder.objects.user_access_filter(user))


class FolderManager(models.Manager):
    """
        Folder manager that can enforce user access perms.
    """
    def get_queryset(self):
        return FolderQuerySet(self.model, using=self._db)

    def user_access_filter(self, user):
        # personal folders
        filter = Q(owned_by=user)

        # vesting org folders
        if user.has_group('registrar_user'):
            filter |= Q(vesting_org__registrar=user.registrar)
        else:
            default_vesting_org = user.get_default_vesting_org()
            if default_vesting_org:
                filter |= Q(vesting_org=default_vesting_org)

        return filter

    def accessible_to(self, user):
        return self.get_queryset().accessible_to(user)


class Folder(MPTTModel):
    name = models.CharField(max_length=255, null=False, blank=False)
    slug = models.CharField(max_length=255, null=False, blank=False)
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children')
    creation_timestamp = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='folders_created',)

    # this may be null if this is the shared folder for a vesting org
    owned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='folders',)

    # this will be set if this is inside a shared folder
    vesting_org = models.ForeignKey(VestingOrg, null=True, blank=True, related_name='folders')

    # true if this is the apex shared folder (not subfolder) for a vesting org
    is_shared_folder = models.BooleanField(default=False)

    # true if this is the apex folder for a user
    is_root_folder = models.BooleanField(default=False)

    objects = FolderManager()

    def __init__(self, *args, **kwargs):
        super(Folder, self).__init__(*args, **kwargs)

        # set defaults
        if not self.pk:
            # set ownership same as parent
            if self.parent:
                if self.parent.vesting_org:
                    self.vesting_org = self.parent.vesting_org
                else:
                    self.owned_by = self.parent.owned_by
            if self.created_by and not self.owned_by and not self.vesting_org:
                self.owned_by = self.created_by
            if not self.slug:
                self.set_slug()

    class MPTTMeta:
        order_insertion_by = ['name']

    def is_empty(self):
        return not self.children.exists() and not self.links.exists()

    def __unicode__(self):
        return self.name

    def contained_links(self):
        return Link.objects.filter(folders__in=self.get_descendants(include_self=True))

    def move_to_folder(self, destination_folder):
        if self.is_shared_folder:
            raise FolderException("Can't move vesting organization's shared folder.")

        if self.is_root_folder:
            raise FolderException("Can't move main folder.")

        if self.vesting_org and self.vesting_org != destination_folder.vesting_org and self.contained_links().filter(vested=True).exists():
            raise FolderException("Can't move folder with vested links out of organization's shared folder.")

        self.parent = destination_folder
        self.set_slug()
        try:
            self.save()
        except InvalidMove:
            raise FolderException("Can't move a folder inside itself.")

        # make sure that child folders share vesting_org and owned_by with new parent folder
        # (one or the other should be set, but not both)
        if destination_folder.vesting_org:
            if self.vesting_org != destination_folder.vesting_org:
                self.get_descendants(include_self=True).update(vesting_org=destination_folder.vesting_org, owned_by=None)
        else:
            if self.owned_by != destination_folder.owned_by:
                self.get_descendants(include_self=True).update(owned_by=destination_folder.owned_by, vesting_org=None)

    def set_slug(self):
        """ Find a slug that doesn't collide with another folder in parent folder. """
        self.slug = slugify(self.name)

        # root folder can't conflict
        if self.is_root_folder:
            return

        if self.is_shared_folder:
            # don't let shared folders collide with any other shared folder
            collision_query = Folder.objects.exclude(pk=self.pk).filter(is_shared_folder=True)
        else:
            # normal folders just can't collide with fellow children of parent
            collision_query = self.parent.get_children().exclude(pk=self.pk)

        i = 1
        while collision_query.filter(slug=self.slug).exists():
            self.slug = "%s-%s" % (slugify(self.name), i)
            i += 1

    def all_children(self):
        """ Return queryset of child folders *including* shared folders if any. """
        filter = Q(parent=self)
        # we show shared folders if user belongs to a vesting org and is viewing their root folder
        if self.is_root_folder and self.owned_by.vesting_org and settings.SHARED_FOLDERS_ENABLED:
            filter |= Q(pk=self.owned_by.vesting_org.shared_folder_id)
        return Folder.objects.filter(filter)

    def display_level(self):
        """
            Get hierarchical level for this folder. If this is a shared folder, level should be one higher
            because it is displayed below user's root folder.
        """
        return self.level + (1 if self.vesting_org_id else 0)


class LinkQuerySet(QuerySet):
    def accessible_to(self, user):
        return self.filter(Link.objects.user_access_filter(user))


class LinkManager(models.Manager):
    """
        Link manager that can enforce user access perms.
    """
    def get_queryset(self):
        return LinkQuerySet(self.model, using=self._db)

    def user_access_filter(self, user):
        """
            User can see/modify a link if they created it or it is in a vesting org folder they belong to, AND it is not deleted
        """
        # personal links
        filter = Q(folders__owned_by=user)

        # links in vesting org folders
        if user.has_group('registrar_user'):
            filter |= Q(folders__vesting_org__registrar=user.registrar)
        else:
            default_vesting_org = user.get_default_vesting_org()
            if default_vesting_org:
                filter |= Q(folders__vesting_org=default_vesting_org)

        # make sure link not deleted
        filter &= Q(user_deleted=False)

        return filter

    def accessible_to(self, user):
        return self.get_queryset().accessible_to(user)

class Link(models.Model):
    """
    This is the core of the Perma link.
    """
    guid = models.CharField(max_length=255, null=False, blank=False, primary_key=True)
    view_count = models.IntegerField(default=1)
    submitted_url = models.URLField(max_length=2100, null=False, blank=False)
    creation_timestamp = models.DateTimeField(auto_now_add=True)
    submitted_title = models.CharField(max_length=2100, null=False, blank=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='created_links',)
    dark_archived = models.BooleanField(default=False)
    dark_archived_robots_txt_blocked = models.BooleanField(default=False)
    user_deleted = models.BooleanField(default=False)
    user_deleted_timestamp = models.DateTimeField(null=True, blank=True)
    vested = models.BooleanField(default=False)
    vested_by_editor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='vested_links')
    vested_timestamp = models.DateTimeField(null=True, blank=True)
    vesting_org = models.ForeignKey(VestingOrg, null=True)
    folders = models.ManyToManyField(Folder, related_name='links', blank=True, null=True)
    notes = models.TextField(blank=True)

    objects = LinkManager()

    def save(self, *args, **kwargs):
        """
        To generate our globally unique identifiers, we draw a number out of a large number space,
        32**8, and convert that to base32 (like base64, but with all caps and without the confusing I,1,O,0 characters)
        so that our URL is short(ish).
        
        One exception - we want to use up our [non-four alphabet chars-anything] ids first. So, avoid things like XFFC-9VS7
        
        """
        initial_folder = kwargs.pop('initial_folder', self.created_by.root_folder)

        if not self.pk and not kwargs.get("pregenerated_guid", False):
            # not self.pk => not created yet
            # only try 100 attempts at finding an unused GUID
            # (100 attempts should never be necessary, since we'll expand the keyspace long before
            # there are frequent collisions)
            for i in range(100):
                random_id = random.randint(0, 32**8)
                guid = base.convert(random_id, base.BASE10, base.BASE32)
                
                # Avoid GUIDs starting with four letters (in case we need those later)
                match = re.search(r'^[A-Z]{4}', guid)
                
                if not match and not Link.objects.filter(guid=guid).exists():
                    break
            else:
                raise Exception("No valid GUID found in 100 attempts.")
            self.guid = Link.get_canonical_guid(guid)
        if "pregenerated_guid" in kwargs:
            del kwargs["pregenerated_guid"]

        super(Link, self).save(*args, **kwargs)

        if not self.folders.count():
            self.folders.add(initial_folder)

    def __unicode__(self):
        return self.submitted_url

    @classmethod
    def get_canonical_guid(self, guid):
        """
        Given a GUID, return the canonical version, with hyphens every 4 chars and all caps.
        So "a2b3c4d5" becomes "A2B3-C4D5".
        """
        # handle legacy 10/11-char GUIDs
        if '-' not in guid and (len(guid) == 10 or len(guid) == 11):
            return guid

        # uppercase and remove non-alphanumerics
        canonical_guid = re.sub('[^0-9A-Z]+', '', guid.upper())

        # split guid into 4-char chunks, starting from the end
        guid_parts = [canonical_guid[max(i - 4, 0):i] for i in
                      range(len(canonical_guid), 0, -4)]

        # stick together parts with '-'
        return "-".join(reversed(guid_parts))

    def move_to_folder_for_user(self, folder, user):
        """
            Move this link to the given folder for the given user.
            If folder is None, link is moved to root (no folder).
        """
        # remove this link from any folders it's in for this user
        self.folders.remove(*self.folders.accessible_to(user))
        # add it back to the given folder
        if folder:
            self.folders.add(folder)

    def generate_storage_path(self):
        """
            Generate the path where assets for this link should be stored.
        """
        if not self.guid:
            raise Exception("Can only generate storage path after link is saved.")
        creation_date = self.creation_timestamp
        return "/".join(str(x) for x in [creation_date.year, creation_date.month, creation_date.day, creation_date.hour, creation_date.minute, self.guid])

    def get_expiration_date(self):
        """ Return date when this link will theoretically be deleted. """
        return self.creation_timestamp + settings.LINK_EXPIRATION_TIME


class Asset(models.Model):
    """
    Our archiving logic generates a bunch of different assets. We store those on disk. We use
    this class to track those locations.
    """
    link = models.ForeignKey(Link, null=False, related_name='assets')
    base_storage_path = models.CharField(max_length=2100, null=True, blank=True) # where we store these assets, relative to some base in our settings
    favicon = models.CharField(max_length=2100, null=True, blank=True) # Retrieved favicon
    image_capture = models.CharField(max_length=2100, null=True, blank=True) # Headless browser image capture
    warc_capture = models.CharField(max_length=2100, null=True, blank=True) # source capture, probably point to an index.html page
    pdf_capture = models.CharField(max_length=2100, null=True, blank=True) # We capture a PDF version (through a user upload or through our capture)
    text_capture = models.CharField(max_length=2100, null=True, blank=True) # We capture a text dump of the resource
    instapaper_timestamp = models.DateTimeField(null=True)
    instapaper_hash = models.CharField(max_length=2100, null=True)
    instapaper_id = models.IntegerField(null=True)

    def __init__(self, *args, **kwargs):
        super(Asset, self).__init__(*args, **kwargs)
        if self.link_id and not self.base_storage_path:
            self.base_storage_path = self.link.generate_storage_path()

    def base_url(self, extra=u""):
        return "%s/%s" % (self.base_storage_path, extra)

    def image_url(self):
        return self.base_url(self.image_capture)

    def warc_url(self):
        if self.warc_capture and '.warc' in self.warc_capture:
            return u"/warc/%s/%s" % (self.link.guid, self.link.submitted_url)
        else:
            return settings.MEDIA_URL+self.base_url(self.warc_capture)

    def warc_download_url(self):
        if '.warc' in self.warc_capture:
            return self.base_url(self.warc_capture)
        return None

    def pdf_url(self):
        return self.base_url(self.pdf_capture)

    def text_url(self):
        return self.base_url(self.text_capture)

    
#########################
# Stats related models
#########################

class Stat(models.Model):
    """
    We have a stats page. A sort of dashboard that displays aggregate counts on users
    and storage space and whatever the heck else might be fun to look at.

    We compute an aggregate count nightly (or whenever we set our celery periodic task to run)
    """

    # The time of this stats entry
    creation_timestamp = models.DateTimeField(auto_now_add=True)

    # Our user counts
    regular_user_count = models.IntegerField(default=1)
    vesting_member_count = models.IntegerField(default=1)
    vesting_manager_count = models.IntegerField(default=1)
    registrar_member_count = models.IntegerField(default=1)
    registry_member_count = models.IntegerField(default=1)

    # Our vesting org count
    vesting_org_count = models.IntegerField(default=1)

    # Our registrar count
    registrar_count = models.IntegerField(default=1)

    # Our link counts
    unvested_count = models.IntegerField(default=1)
    vested_count = models.IntegerField(default=1)
    darchive_takedown_count = models.IntegerField(default=0)
    darchive_robots_count = models.IntegerField(default=0)    

    # Our google analytics counts
    global_uniques = models.IntegerField(default=1)

    # Our size count
    disk_usage = models.FloatField(default=0.0)

    # TODO, we also display the top 10 perma links in the stats view
    # we should probably generate these here or put them in memcache or something
