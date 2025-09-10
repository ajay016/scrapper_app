from rest_framework import serializers
from .models import *










class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "user_type", "role"]

    def get_role(self, obj):
        return obj.get_user_type_display()
    

class KeywordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Keyword
        fields = ['id', 'word']

class SearchResultLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchResultLink
        fields = ['id', 'url', 'title', 'name', 'crawled_at']

class ProjectFolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectFolder
        fields = ["id", "name"]

class ProjectSerializer(serializers.ModelSerializer):
    folders = ProjectFolderSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = ["id", "name", "folders"]