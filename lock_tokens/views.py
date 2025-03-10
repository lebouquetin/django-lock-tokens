from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from lock_tokens.exceptions import AlreadyLockedError
from lock_tokens.models import LockToken
from lock_tokens.settings import API_CSRF_EXEMPT


def lock_tokens_csrf_exempt(view):
    return csrf_exempt(view) if API_CSRF_EXEMPT else view


class LockTokenBaseView(View):

    @method_decorator(lock_tokens_csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(LockTokenBaseView, self).dispatch(*args, **kwargs)

    def get_contenttype_or_404(self, app_label, model):
        try:
            return ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            raise Http404(
                "There is no model named %s with app_label %s" % (model, app_label)
            )

    def get_object_or_404(self, app_label, model, object_id):
        contenttype = self.get_contenttype_or_404(app_label, model)
        try:
            return contenttype.get_object_for_this_type(id=object_id)
        except contenttype.model_class().DoesNotExist:
            raise Http404("The object with id %s does not exist" % object_id)

    def get_valid_lock_token_or_error(
        self, app_label, model, object_id, token, allow_expired=True
    ):
        contenttype = self.get_contenttype_or_404(app_label, model)
        try:
            lock_token = LockToken.objects.get_for_contenttype_and_id(
                contenttype, object_id, allow_expired
            )
        except LockToken.DoesNotExist:
            raise Http404("No valid token for this resource.")
        if not token == lock_token.token_str:
            raise PermissionDenied("Wrong token.")
        return lock_token


class LockTokenListView(LockTokenBaseView):

    def post(self, request, app_label, model, object_id):
        obj = self.get_object_or_404(app_label, model, object_id)
        try:
            lock_token = LockToken.objects.create(locked_object=obj)
        except AlreadyLockedError:
            return JsonResponse(
                {}, status=409, reason="This resource is " "already locked"
            )
        return JsonResponse(lock_token.serialize(), status=201)


class LockTokenDetailView(LockTokenBaseView):

    def get(self, request, app_label, model, object_id, token):
        lock_token = self.get_valid_lock_token_or_error(
            app_label, model, object_id, token
        )
        return JsonResponse(lock_token.serialize())

    def patch(self, request, app_label, model, object_id, token):
        lock_token = self.get_valid_lock_token_or_error(
            app_label, model, object_id, token
        )
        lock_token.renew()
        return JsonResponse(lock_token.serialize())

    def delete(self, request, app_label, model, object_id, token):
        lock_token = self.get_valid_lock_token_or_error(
            app_label, model, object_id, token
        )
        lock_token.delete()
        return JsonResponse({}, status=204)
