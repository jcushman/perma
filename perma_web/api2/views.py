import django_filters
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.http import Http404
from mptt.exceptions import InvalidMove
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import DjangoFilterBackend, SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from perma.utils import run_task
from perma.tasks import upload_to_internet_archive, delete_from_internet_archive, run_next_capture
from perma.models import Folder, CaptureJob, Link, Capture, Organization

from utils import TastypiePagination, bad_request, load_parent, log_api_call
from serializers import FolderSerializer, CaptureJobSerializer, LinkSerializer, AuthenticatedLinkSerializer, \
    LinkUserSerializer, OrganizationSerializer


### BASE VIEW ###

class BaseView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = None

    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    ordering_fields = ()  # override this to allow ordering

    ### helpers ###

    def filter_queryset(self, queryset):
        """
        Given a queryset, filter it with whichever filter backend is in use.

        Copied from GenericAPIView
        """
        try:
            for backend in list(self.filter_backends):
                queryset = backend().filter_queryset(self.request, queryset, self)
            return queryset
        except DjangoValidationError as e:
            raise ValidationError(e.error_dict)

    def get_object_for_user(self, user, queryset):
        try:
            obj = queryset.get()
        except ObjectDoesNotExist:
            raise Http404
        if not obj.accessible_to(user):
            raise PermissionDenied()
        return obj

    def get_object_for_user_by_pk(self, user, pk):
        ModelClass = self.serializer_class.Meta.model
        return self.get_object_for_user(user, ModelClass.objects.filter(pk=pk))

    ### basic views ###

    def simple_list(self, request, queryset):
        queryset = self.filter_queryset(queryset)
        paginator = TastypiePagination()
        items = paginator.paginate_queryset(queryset, request)
        serializer = self.serializer_class(items, many=True)
        return paginator.get_paginated_response(serializer.data)

    def simple_get(self, request, pk=None, obj=None):
        if not obj:
            obj = self.get_object_for_user_by_pk(request.user, pk)
        serializer = self.serializer_class(obj)
        return Response(serializer.data)

    def simple_create(self, data, save_kwargs={}):
        serializer = self.serializer_class(data=data, context={'request': self.request})
        if serializer.is_valid():
            serializer.save(**save_kwargs)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def simple_update(self, obj, data):
        serializer = self.serializer_class(obj, data=data, partial=True, context={'request': self.request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        raise ValidationError(serializer.errors)

    def simple_delete(self, obj):
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


### ORGANIZATION VIEWS ###

class OrganizationListView(BaseView):
    serializer_class = OrganizationSerializer
    ordering_fields = ('name', 'registrar__name')

    @load_parent
    def get(self, request, format=None):
        queryset = Organization.objects.accessible_to(request.user).select_related('registrar', 'shared_folder')
        return self.simple_list(request, queryset)

class OrganizationDetailView(BaseView):
    serializer_class = OrganizationSerializer

    @load_parent
    def get(self, request, pk, format=None):
        return self.simple_get(request, pk)


### FOLDER VIEWS ###

class FolderListView(BaseView):
    serializer_class = FolderSerializer

    @load_parent
    def get(self, request, format=None):
        if request.parent:
            queryset = Folder.objects.filter(parent=request.parent)
        else:
            queryset = request.user.top_level_folders()
        return self.simple_list(request, queryset)

    @load_parent
    def post(self, request, format=None):
        data = request.data.copy()
        if request.parent:
            data['parent'] = request.parent.pk
        return self.simple_create(data, {'created_by': request.user})

class FolderDetailView(BaseView):
    serializer_class = FolderSerializer

    @load_parent
    def get(self, request, pk, format=None):
        return self.simple_get(request, pk)

    @load_parent
    def patch(self, request, pk, format=None):
        return self.folder_update(request, pk, request.data)

    @load_parent
    def put(self, request, pk, format=None):
        return self.folder_update(request, pk, {'parent': request.parent.pk})

    @load_parent
    def delete(self, request, pk, format=None):
        folder = self.get_object_for_user_by_pk(request.user, pk)

        # delete validations
        if folder.is_shared_folder:
            return bad_request("Shared folders cannot be deleted.")
        elif folder.is_root_folder:
            return bad_request("Root folders cannot be deleted.")
        elif not folder.is_empty():
            return bad_request("Folders can only be deleted if they are empty.")

        return self.simple_delete(folder)

    def folder_update(self, request, pk, data):
        obj = self.get_object_for_user_by_pk(request.user, pk)
        try:
            return self.simple_update(obj, data)
        except InvalidMove as e:
            return Response({"parent":e.args[0]}, status=status.HTTP_400_BAD_REQUEST)


### CAPTUREJOB VIEWS ###

class CaptureJobListView(BaseView):
    serializer_class = CaptureJobSerializer

    def get(self, request, format=None):
        queryset = CaptureJob.objects.filter(link__created_by_id=request.user.pk, status__in=['pending', 'in_progress'])
        return self.simple_list(request, queryset)


class CaptureJobDetailView(BaseView):
    serializer_class = CaptureJobSerializer

    def get(self, request, pk=None, guid=None, format=None):
        if guid:
            obj = self.get_object_for_user(request.user, CaptureJob.objects.filter(link_id=guid).select_related('link'))
            return self.simple_get(request, obj=obj)
        else:
            return self.simple_get(request, pk)


### LINK VIEWS ###

class LinkFilter(django_filters.rest_framework.FilterSet):
    date = django_filters.IsoDateTimeFilter(name="creation_timestamp", lookup_expr='date')
    min_date = django_filters.IsoDateTimeFilter(name="creation_timestamp", lookup_expr='gte')
    max_date = django_filters.IsoDateTimeFilter(name="creation_timestamp", lookup_expr='lte')
    url = django_filters.CharFilter(name="submitted_url", lookup_expr='icontains')
    class Meta:
        model = Link
        fields = ['url', 'date', 'min_date', 'max_date']


class PublicLinkListView(BaseView):
    permission_classes = ()
    serializer_class = LinkSerializer
    filter_class = LinkFilter
    search_fields = ('guid', 'submitted_url', 'submitted_title', 'notes')

    def get(self, request, format=None):
        queryset = Link.objects.order_by('-creation_timestamp').prefetch_related('captures').discoverable()
        return self.simple_list(request, queryset)

class PublicLinkDetailView(BaseView):
    permission_classes = ()
    serializer_class = LinkSerializer

    def get(self, request, guid, format=None):
        try:
            obj = Link.objects.discoverable().get(pk=guid)
        except Link.DoesNotExist:
            raise Http404
        return self.simple_get(request, obj=obj)

class AuthenticatedLinkListView(BaseView):
    serializer_class = AuthenticatedLinkSerializer
    filter_class = LinkFilter
    search_fields = PublicLinkListView.search_fields + ('notes',)

    @staticmethod
    def get_folder_from_request(request):
        if request.data.get('folder'):
            try:
                return Folder.objects.accessible_to(request.user).get(pk=request.data['folder'])
            except Folder.DoesNotExist:
                raise ValidationError({'folder': "Folder not found."})
        return None

    @load_parent
    def get(self, request, format=None):
        queryset = Link.objects\
            .order_by('-creation_timestamp')\
            .select_related('organization', 'organization__registrar','capture_job')\
            .prefetch_related('captures')\
            .accessible_to(request.user)
        if request.parent:
            queryset = queryset.filter(folders=request.parent)
        return self.simple_list(request, queryset)

    @load_parent
    def post(self, request, format=None):
        data = request.data

        # set target folder
        folder = self.get_folder_from_request(request) or request.folder or request.user.root_folder

        # Make sure a limited user has links left to create
        if not folder.organization:
            links_remaining = request.user.get_links_remaining()
            if links_remaining < 1:
                raise ValidationError({'error': "You've already reached your limit."})

        serializer = self.serializer_class(data=data, context={'request': request})
        if serializer.is_valid():

            link = serializer.save(created_by=request.user)

            # put link in folder and handle Org settings based on folder
            if folder.organization and folder.organization.default_to_private:
                link.is_private = True
                link.save()
            link.move_to_folder_for_user(folder, request.user)  # also sets link.organization

            # handle uploaded file
            uploaded_file = request.data.get('file')
            if uploaded_file:
                link.write_uploaded_file(uploaded_file)

            # handle submitted url
            else:
                # create primary capture placeholder
                Capture(
                    link=link,
                    role='primary',
                    status='pending',
                    record_type='response',
                    url=link.submitted_url,
                ).save()

                # create screenshot placeholder
                Capture(
                    link=link,
                    role='screenshot',
                    status='pending',
                    record_type='resource',
                    url="file:///%s/cap.png" % link.guid,
                    content_type='image/png',
                ).save()

                # create CaptureJob
                CaptureJob(link=link, human=request.data.get('human', False)).save()

                # kick off capture tasks -- no need for guid since it'll work through the queue
                run_task(run_next_capture.s())

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AuthenticatedLinkDetailView(BaseView):
    serializer_class = AuthenticatedLinkSerializer

    def get(self, request, guid, format=None):
        return self.simple_get(request, guid)

    @log_api_call
    def patch(self, request, guid, format=None):
        link = self.get_object_for_user_by_pk(request.user, guid)

        was_private = link.is_private
        data = request.data

        serializer = self.serializer_class(link, data=data, partial=True, context={'request': self.request})
        if serializer.is_valid():
            serializer.save()

            # move to new folder
            folder = AuthenticatedLinkListView.get_folder_from_request(request)
            if folder:
                link.move_to_folder_for_user(folder, request.user)

            # handle file patch
            uploaded_file = request.data.get('file')
            if uploaded_file:

                # delete related cdxlines and captures, delete warc (rename)
                link.delete_related()
                link.safe_delete_warc()

                # write new warc and capture
                link.write_uploaded_file(uploaded_file, cache_break=True)

            # update internet archive if privacy changes
            if 'is_private' in data:
                if link.is_archive_eligible():
                    going_private = data.get("is_private")
                    # if link was private but has been marked public
                    if was_private and not going_private:
                        run_task(upload_to_internet_archive.s(link_guid=link.guid))

                    # if link was public but has been marked private
                    elif not was_private and going_private:
                        run_task(delete_from_internet_archive.s(link_guid=link.guid))

            # include remaining links in response
            links_remaining = request.user.get_links_remaining()
            serializer.data['links_remaining'] = links_remaining

            # clear out cache -- for privacy and warc replacement
            link.clear_cache()

            return Response(serializer.data)

        raise ValidationError(serializer.errors)

    def delete(self, request, guid, format=None):
        link = self.get_object_for_user_by_pk(request.user, guid)

        if not request.user.can_delete(link):
            raise PermissionDenied()

        link.delete_related()  # deleting related captures and cdxlines
        link.safe_delete()
        link.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

class MoveLinkView(BaseView):
    serializer_class = AuthenticatedLinkSerializer

    @load_parent
    def put(self, request, guid, format=None):
        link = self.get_object_for_user_by_pk(request.user, guid)
        link.move_to_folder_for_user(request.parent, request.user)
        serializer = self.serializer_class(link)
        return Response(serializer.data)


### LINKUSER ###

class LinkUserView(BaseView):
    serializer_class = LinkUserSerializer

    @load_parent
    def get(self, request, format=None):
        serializer = self.serializer_class(request.user)
        return Response(serializer.data)

