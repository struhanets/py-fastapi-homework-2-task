import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from database import get_db, MovieModel
from database.models import GenreModel, ActorModel, LanguageModel

from schemas.movies import MoviesListSchema, MovieDetailSchema, MovieCreateSchema, MoviePatchSchema, \
    MovieListResponseSchema
from sources.movie_create import (
    check_if_movie_exist,
    get_or_create_country,
    get_or_create_entity,
    create_movie_instance,
    get_movie_or_404,
)

router = APIRouter()


@router.get("/")
def read_root():
    return {"message": ""}


@router.get("/movies/", response_model=MoviesListSchema)
async def get_movies(
        page: int = Query(1, ge=1),
        per_page: int = Query(10, ge=1, le=20),
        db: AsyncSession = Depends(get_db)
):
    # Порахувати всі елементи, щоб можна було потім їх розприділити по сторінках
    total_items = await db.scalar(select(func.count()).select_from(MovieModel))

    # Вичисляємо загальну кільксть сторінок, навіть при умові що сторнка може бути не повна і містити іншу кількість
    # елементів
    total_pages = math.ceil(total_items / per_page)

    # визначаємо offcet тобто к-сть записів які ми будемо зміщувати при вибірці
    offset = (page - 1) * per_page
    # ну і нарешті проводимо саму вибірку
    request = (
        select(MovieModel)
        .order_by(MovieModel.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(request)
    movies = result.scalars().all()

    if not movies:
        raise HTTPException(status_code=404, detail="No movies found.")

    # Це list comprehension, який перетворює список об'єктів movies (отриманих з бази даних через SQLAlchemy) у
    # список об'єктів-схем типу MovieDetailResponseSchema
    movies_schema = [MovieListResponseSchema.model_validate(movie, from_attributes=True) for movie in movies]

    base_url = "/theater/movies/"
    prev_page = f"{base_url}?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = f"{base_url}?page={page + 1}&per_page={per_page}" if page < total_pages else None

    return MoviesListSchema(
        movies=movies_schema,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items
    )


@router.post("/movies/", response_model=MovieDetailSchema, status_code=201)
async def create_movie(
        movie: MovieCreateSchema,
        db: AsyncSession = Depends(get_db)
):
    await check_if_movie_exist(movie.name, movie.date, db)

    country = await get_or_create_country(
        code=movie.country,
        name=None,
        db=db
    )
    genres = await get_or_create_entity(GenreModel, movie.genres, db)
    actors = await get_or_create_entity(ActorModel, movie.actors, db)
    languages = await get_or_create_entity(LanguageModel, movie.languages, db)

    new_movie = create_movie_instance(None, movie, country, actors, genres, languages)

    db.add(new_movie)
    await db.commit()
    # необхідне при асинхронній роботі, щоб перед створенням підгружались пов*язані моделі
    stmt = (
        select(MovieModel)
        .where(MovieModel.id == new_movie.id)
        .options(
            selectinload(MovieModel.genres),
            selectinload(MovieModel.actors),
            selectinload(MovieModel.languages),
            selectinload(MovieModel.country),
        )
    )
    result = await db.execute(stmt)
    created_movie = result.scalar_one()
    return MovieDetailSchema.model_validate(created_movie, from_attributes=True)


@router.get("/movies/{movie_id}/", response_model=MovieDetailSchema)
async def get_movie(
        movie_id: int,
        db: AsyncSession = Depends(get_db)
):
    movie = await get_movie_or_404(movie_id, db)
    return MovieDetailSchema.model_validate(movie, from_attributes=True)


@router.patch("/movies/{movie_id}/", response_model=dict)
async def update_movie(
    movie_id: int,
    data: MoviePatchSchema,
    db: AsyncSession = Depends(get_db)
):
    movie = await get_movie_or_404(movie_id, db)

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(movie, field, value)

    await db.commit()
    return {"detail": "Movie updated successfully."}


@router.delete("/movies/{movie_id}/", status_code=204)
async def delete_movie(
        movie_id: int,
        db: AsyncSession = Depends(get_db)
):
    movie = await get_movie_or_404(movie_id, db)
    await db.delete(movie)
    await db.commit()
    return Response(status_code=204)
