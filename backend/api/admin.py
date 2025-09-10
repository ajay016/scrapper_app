from django.contrib import admin
from .models import *





@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'first_name', 'last_name', 'user_type', 'user_status', 'is_staff')
    list_filter = ('user_type', 'user_status', 'is_staff', 'is_active', 'subscription_status')
    search_fields = ('email', 'username', 'first_name', 'last_name', 'phone_number', 'user_id')
    ordering = ('email',)
    fieldsets = (
        ('User Information', {'fields': ('email', 'username', 'first_name', 'last_name', 'phone_number', 'address', 'city', 'state', 'postal_code')}),
        ('Status & Permissions', {'fields': ('user_type', 'user_status', 'subscription_status', 'is_staff', 'is_active')}),
    )
    readonly_fields = ('user_id',)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'gender', 'date_of_birth', 'job_title', 'country')
    search_fields = ('user__username', 'user__email', 'job_title')
    list_filter = ('gender', 'country')
    raw_id_fields = ('user',)

# ------------------------------------------------------------
# Admin for Project and Keyword models
# ------------------------------------------------------------

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at')
    search_fields = ('name', 'user__username', 'user__email')
    list_filter = ('created_at',)
    raw_id_fields = ('user',)
    
    
@admin.register(ProjectFolder)
class ProjectFolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'user_email', 'description', 'created_at')
    list_display_links = ('name',)
    list_select_related = ('project', 'project__user')
    search_fields = ('name', 'project__name', 'project__user__email')
    list_filter = ('project', 'created_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    
    @admin.display(description="User Email")
    def user_email(self, obj):
        return obj.project.user.email if obj.project and obj.project.user else 'N/A'
    

@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ('word', 'user', 'created_at')
    search_fields = ('word', 'user__username', 'user__email')
    list_filter = ('created_at',)
    raw_id_fields = ('user',)

# ------------------------------------------------------------
# Admin for Search and Crawling models
# ------------------------------------------------------------

@admin.register(SearchJob)
class SearchJobAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'status', 'created_at', 'finished_at')
    search_fields = ('name', 'user__username', 'user__email')
    list_filter = ('status', 'created_at', 'finished_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'

@admin.register(SearchSetting)
class SearchSettingAdmin(admin.ModelAdmin):
    list_display = ('job', 'results_per_keyword', 'crawl_depth', 'crawl_entire_domain')
    list_filter = ('crawl_entire_domain',)
    raw_id_fields = ('job',)

@admin.register(SearchResultLink)
class SearchResultLinkAdmin(admin.ModelAdmin):
    list_display = ('display_label', 'keyword', 'user', 'url', 'parent', 'depth', 'crawled_at')
    list_display_links = ('display_label',)
    list_select_related = ('user', 'keyword', 'job', 'parent')  # Optimized FK fetching
    search_fields = (
        "keyword__word",
        "name",
        "title",
        "url",
        "user__email",
        "user__username",
        "user__first_name",
        "user__last_name",
    )
    list_filter = ('user', 'crawled_at', 'depth')
    date_hierarchy = 'crawled_at'
    ordering = ('-crawled_at',)
    readonly_fields = ('crawled_at',)
    raw_id_fields = ('keyword', 'job', 'user', 'parent')
    
    @admin.display(description="Result")
    def display_label(self, obj):
        return obj.name or obj.title or obj.url

@admin.register(CrawledPage)
class CrawledPageAdmin(admin.ModelAdmin):
    list_display = ('url', 'title', 'depth', 'result')
    search_fields = ('url', 'title')
    list_filter = ('depth',)
    raw_id_fields = ('result',)
