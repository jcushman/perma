from django.conf import settings
from django.core.validators import URLValidator
from requests import TooManyRedirects
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from utils import get_mime_type, mime_type_lookup
from perma.models import LinkUser, Folder, CaptureJob, Capture, Link, Organization
from perma.utils import ip_in_allowed_ip_range


class BaseSerializer(serializers.ModelSerializer):
    def update(self, instance, validated_data):
        if set(validated_data.keys()) - set(self.Meta.allowed_update_fields):
            raise ValidationError('Only updates on these fields are allowed: %s' % ', '.join(self.allowed_update_fields))
        return super(BaseSerializer, self).update(instance, validated_data)


### LINKUSER ###

class NestedLinkUserSerializer(BaseSerializer):
    full_name = serializers.ReadOnlyField(source='get_full_name')
    short_name = serializers.ReadOnlyField(source='get_short_name')

    class Meta:
        model = LinkUser
        fields = ('id', 'first_name', 'last_name', 'full_name', 'short_name')

class LinkUserSerializer(NestedLinkUserSerializer):
    top_level_folders = serializers.SerializerMethodField()

    class Meta(NestedLinkUserSerializer.Meta):
        fields = NestedLinkUserSerializer.Meta.fields + ('top_level_folders',)

    def get_top_level_folders(self, user):
        serializer = FolderSerializer(user.top_level_folders(), many=True)
        return serializer.data


### FOLDER ###

class FolderSerializer(BaseSerializer):
    has_children = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = ('id', 'name', 'parent', 'has_children', 'organization')
        extra_kwargs = {'parent': {'required': True}}
        allowed_update_fields = ['name', 'parent']

    def get_has_children(self, folder):
        return not folder.is_leaf_node()

    def validate_name(self, name):
        if self.instance:
            # renaming
            if self.instance.is_shared_folder:
                raise serializers.ValidationError("Shared folders cannot be renamed.")
            if self.instance.is_root_folder:
                raise serializers.ValidationError("User's main folder cannot be renamed.")
        return name

    def validate_parent(self, parent_id):
        if not parent_id:
            raise serializers.ValidationError("Can't move folder to top level.")
        if self.instance:
            # moving
            if self.instance.is_shared_folder:
                raise serializers.ValidationError("Can't move organization's shared folder.")
            if self.instance.is_root_folder:
                raise serializers.ValidationError("Can't move user's main folder.")
        return parent_id

    def validate(self, data):
        if 'name' in data:
            # make sure name is unique in this location
            parent_id = data['parent_id'] if 'parent_id' in data else \
                        data['parent'].pk if 'parent' in data else \
                        self.instance.parent_id if self.instance else None
            if parent_id:
                unique_query = Folder.objects.filter(parent_id=parent_id, name=data['name'])
                if self.instance:
                    unique_query = unique_query.exclude(pk=self.instance.pk)
                if unique_query.exists():
                    raise serializers.ValidationError({'name':"A folder with that name already exists at that location."})
        return data


### ORGANIZATION ###

class OrganizationSerializer(BaseSerializer):
    registrar = serializers.StringRelatedField()
    shared_folder = FolderSerializer()

    class Meta:
        model = Organization
        fields = ('id', 'name', 'registrar', 'default_to_private', 'shared_folder')


### CAPTUREJOB ###

class CaptureJobSerializer(BaseSerializer):
    guid = serializers.PrimaryKeyRelatedField(source='link', read_only=True)
    class Meta:
        model = CaptureJob
        fields = ('guid', 'status', 'attempt', 'step_count', 'step_description', 'capture_start_time', 'capture_end_time', 'queue_position')


### CAPTURE ###

class CaptureSerializer(BaseSerializer):
    class Meta:
        model = Capture
        fields = ('role', 'status', 'url', 'record_type', 'content_type', 'user_upload', 'playback_url')


### LINK ###

class LinkSerializer(BaseSerializer):
    url = serializers.CharField(source='submitted_url', max_length=2100, required=False, allow_blank=True)
    title = serializers.CharField(source='submitted_title', max_length=2100, required=False)
    description = serializers.CharField(source='submitted_description', allow_blank=True, allow_null=True, max_length=300, required=False)

    captures = CaptureSerializer(many=True, read_only=True)
    queue_time = serializers.SerializerMethodField()
    capture_time = serializers.SerializerMethodField()

    class Meta:
        model = Link
        fields = ('guid', 'creation_timestamp', 'url', 'title', 'description', 'warc_size', 'captures', 'queue_time', 'capture_time')

    def get_queue_time(self, link):
        try:
            delta = link.capture_job.capture_start_time - link.creation_timestamp
            return delta.seconds
        except:
            return None

    def get_capture_time(self, link):
        try:
            delta = link.capture_job.capture_end_time - link.capture_job.capture_start_time
            return delta.seconds
        except:
            return None


class AuthenticatedLinkSerializer(LinkSerializer):
    created_by = NestedLinkUserSerializer(read_only=True)
    organization = OrganizationSerializer(read_only=True)

    class Meta(LinkSerializer.Meta):
        fields = LinkSerializer.Meta.fields + ('notes', 'created_by', 'is_private', 'private_reason', 'archive_timestamp', 'organization')
        allowed_update_fields = ['submitted_title', 'submitted_description', 'notes', 'is_private', 'private_reason']

    def validate_url(self, url):
        # Clean up the user submitted url
        url = url.strip()
        if url and url[:4] != 'http':
            url = 'http://' + url
        return url

    def validate(self, data):
        user = self.context['request'].user

        # handle private_reason
        if not user.is_staff:
            data.pop('private_reason', None)
        if self.instance:
            if 'is_private' in data:
                toggled_private = self.instance.is_private != bool(data['is_private'])
                if toggled_private and not user.is_staff:
                    if self.instance.private_reason and self.instance.private_reason != 'user':
                        raise ValidationError({'is_private':'Cannot change link privacy.'})
                    data['private_reason'] = 'user' if data['is_private'] else None
        else:
            # for new links, set private_reason based on is_private
            data['private_reason'] = 'user' if data.get('is_private') else None

        errors = {}

        # check submitted URL for new link
        if not self.instance:
            if not data.get('submitted_url'):
                errors['url'] = "URL cannot be empty."
            else:
                try:
                    validate = URLValidator()
                    temp_link = Link(submitted_url=data['submitted_url'])
                    validate(temp_link.safe_url)

                    # Don't force URL resolution validation if a file is provided
                    if not data.get('file'):
                        if not temp_link.ip:
                            errors['url'] = "Couldn't resolve domain."
                        elif not ip_in_allowed_ip_range(temp_link.ip):
                            errors['url'] = "Not a valid IP."
                        elif not temp_link.headers:
                            errors['url'] = "Couldn't load URL."
                        else:
                            # preemptively reject URLs that report a size over settings.MAX_ARCHIVE_FILE_SIZE
                            try:
                                if int(temp_link.headers.get('content-length', 0)) > settings.MAX_ARCHIVE_FILE_SIZE:
                                    errors['url'] = "Target page is too large (max size %sMB)." % (settings.MAX_ARCHIVE_FILE_SIZE / 1024 / 1024)
                            except ValueError:
                                # content-length header wasn't an integer. Carry on.
                                pass
                except UnicodeError:
                    # see https://github.com/harvard-lil/perma/issues/1841
                    errors['url'] = "Unicode error while processing URL."
                except ValidationError:
                    errors['url'] = "Not a valid URL."
                except TooManyRedirects:
                    errors['url'] = "URL caused a redirect loop."

        # check uploaded file
        uploaded_file = self.context['request'].data.get('file')
        if uploaded_file == '':
            errors['file'] = "File cannot be blank."
        if uploaded_file:

            if self.instance and self.instance.is_archive_eligible():
                errors['file'] = "Archive contents cannot be replaced after 24 hours"

            else:
                mime_type = get_mime_type(uploaded_file.name)

                # Get mime type string from tuple
                if not mime_type or not mime_type_lookup[mime_type]['valid_file'](uploaded_file):
                    errors['file'] = "Invalid file."
                elif uploaded_file.size > settings.MAX_ARCHIVE_FILE_SIZE:
                    errors['file'] = "File is too large."

        if errors:
            raise serializers.ValidationError(errors)

        return data

