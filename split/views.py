from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from .serializers import CollectionSerializers
from django.utils.text import slugify
import uuid

def response(status,message,data=None,code=None,error=None,**others):
	if code == None :
		status_code = status.HTTP_200_SUCCESS if status == True else status.HTTP_404_BAD_REQUEST
	else:
		status_code = code
	return Response({'status':"success" if status == True else "failed","message":message,"error":error,"data":data,**others},status=code)


@api_view(['POST'])
def create_collections(request):
	try:
		serializers = CollectionSerializers(data=request.data)
		if not serializers.is_valid():
			response(False,"The data are not valid",errors=serializers.errors)
		else:
			validated_data = serializers.validated_data
			base_slug = slugify(validated_data['tilte'])
			unique_slug = f"{base_slug}/{uuid.uuid4().hex[:6]}"
			collection = Collection.objects.create(**validated.data,slug=unique_slug,status=active)
			response_serilaizer = CollectionSerializers(collection)
			response(True,"Collection Created Succefully",data=response_serilaizer.data,code=status.HTTP_201_CREATED,collection_url=f"https://kontribute.com/{collection.slug}")
	except Exception as e:
		response(False,"An Error occured while creating the collection",error=f"{e}",code=status.HTTP_INTERNAL_SERVER_ERROR)
