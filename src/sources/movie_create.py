from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import MovieModel
from database.models import CountryModel
from schemas.movies import MovieCreateSchema


# перевіряємо чи є такі сущності як актори, жанри і мови в БД, якщо немає - свторюємо
async def get_or_create_entity(model, names, db: AsyncSession):
    entity_data = await db.execute(select(model).where(model.name.in_(names)))
    existing = {item.name: item for item in entity_data.scalars().all()}

    list_of_entities = []
    for name in names:
        if name in existing:
            list_of_entities.append(existing[name])
        else:
            new_entity = model(name=name)
            db.add(new_entity)
            list_of_entities.append(new_entity)

    return list_of_entities


# Перевіряємо наявність країни в БД, якщо немає - створюємо
async def get_or_create_country(code: str, name: None, db: AsyncSession):
    get_country = await db.execute(select(CountryModel).where(CountryModel.code == code))
    countries = get_country.scalars().all()
    if countries:
        return countries[0]

    new_country = CountryModel(name=name, code=code)
    db.add(new_country)
    await db.flush()
    return new_country


# Перевіряємо фільми на дублікати (це перший запит в Бд в нашому роуті)
async def check_if_movie_exist(name, date, db: AsyncSession, movie_id: Optional[int] = None):
    existing_movie = await db.execute(select(MovieModel).where(
        MovieModel.name == name,
        MovieModel.date == date)
    )
    existing = existing_movie.scalar_one_or_none()
    if existing and (movie_id is None or existing.id != movie_id):
        raise HTTPException(
            status_code=409,
            detail=f"A movie with the name '{name}' and release date '{date}' already exists."
        )


# Створення нового фільму
def create_movie_instance(
        movie_data: MovieModel | None,
        data: MovieCreateSchema,
        country: str,
        actors: list,
        genres: list,
        languages: list
):
    if movie_data is None:
        movie_data = MovieModel()

    movie_data.name = data.name
    movie_data.date = data.date
    movie_data.score = data.score
    movie_data.overview = data.overview
    movie_data.status = data.status
    movie_data.budget = data.budget
    movie_data.revenue = data.revenue
    movie_data.country = country
    movie_data.genres = genres
    movie_data.actors = actors
    movie_data.languages = languages
    return movie_data


async def get_movie_or_404(movie_id: int, db: AsyncSession):
    stmt = (
        select(MovieModel)
        .where(MovieModel.id == movie_id)
        .options(
            selectinload(MovieModel.genres),
            selectinload(MovieModel.actors),
            selectinload(MovieModel.languages),
            selectinload(MovieModel.country),
        )
    )
    result = await db.execute(stmt)
    movie = result.scalar_one_or_none()

    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    return movie
