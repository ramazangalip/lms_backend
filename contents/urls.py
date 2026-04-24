from django.urls import path
from .views import *

urlpatterns = [
    path('pre-test/submit/', PreTestSubmitView.as_view(), name='pre-test-submit'),
    path('pre-test/status/', PreTestStatusView.as_view(), name='pre-test-status'),
    # Hem öğrencilerin listelemesi hem de hocaların içerik eklemesi için ortak endpoint
    path('list/', WeeklyContentView.as_view(), name='weekly_contents_list'),
    
    # Belirli bir haftanın detaylarını (video ve podcast listesini) getirmek için
    path('week/<int:week_number>/', ContentDetailView.as_view(), name='week_detail'),

    # Öğrencinin veri göndereceği endpoint
    path('track-activity/', TrackActivityView.as_view(), name='track_activity'),
    
    # Hocanın tüm öğrencileri göreceği endpoint
    path('teacher/analytics/', TeacherAnalyticsView.as_view(), name='teacher_analytics'),
    
    # Hocanın spesifik bir öğrenci detayını göreceği endpoint
    path('teacher/analytics/<int:student_id>/', TeacherAnalyticsView.as_view(), name='student_detail_analytics'),

    path('complete-material/', CompleteMaterialView.as_view(), name='complete_material'),
    path('completed-materials-ids/', CompletedMaterialIdsView.as_view(), name='completed_mats_ids'),
    path('studentprogress/', StudentProgressListView.as_view(), name='student_progress_list'),
    path('analytics/', StudentAnalyticsView.as_view(), name='student_analytics'),
    path('ai-chat/', AIChatView.as_view(), name='ai_chat'),
    path('quiz/<int:quiz_id>/submit/', QuizSubmitView.as_view(), name='quiz-submit'),
    path('quiz-analysis/<int:attempt_id>/', QuizAIAnalysisView.as_view(), name='quiz-ai-analysis'),
    path('quiz/<int:quiz_id>/last-attempt/', QuizLastAttemptView.as_view(), name='quiz-last-attempt'),
    path('weeks/complete-intro/', CompleteIntroVideoView.as_view(), name='complete-intro'),
    path('bulk-academic-report/', BulkAcademicReportView.as_view(), name='bulk-report'),
    path('chatbot-analytics/', ChatbotAnalyticsView.as_view(), name='chatbot-analytics'),
    path('week/<int:week_number>/submit-entry-test/', WeeklyPreTestSubmitView.as_view(), name='weekly-entry-test-submit'),
    path('student-badges/', StudentBadgeListView.as_view(), name='student-badges'),
    
    path('surveys/week/<int:week_number>/', SurveyDetailView.as_view(), name='survey-detail'),
    path('academic/surveys/report/', AcademicSurveyAnalyticsView.as_view(), name='survey-report'),

]