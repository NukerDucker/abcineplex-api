# services/movie_service.py
from app.core.supabase import supabase
from app.schemas.movie import MovieCreate

def create_movie(movie: MovieCreate):
    data = movie.model_dump(mode='json')
    response = supabase.table("movies").insert(data).execute()
    return response.data

def get_movies():
    response = supabase.table("movies").select("*").execute()
    return response.data