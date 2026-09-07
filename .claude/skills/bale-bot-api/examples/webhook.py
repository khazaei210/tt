# Illustrative Django webhook shape. Adapt to the project's auth, routing and Celery conventions.
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json


@csrf_exempt
@require_POST
def bale_webhook(request):
    update = json.loads(request.body)

    # Dispatch quickly; long-running work should be queued.
    # process_bale_update.delay(update)

    return JsonResponse({"ok": True})
