import json
import random
from datetime import datetime
from typing import Type
from pathlib import Path
from dataclasses import asdict

from sqlalchemy import create_engine, text, update, func
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session, sessionmaker, joinedload

from core.db_utils.models import Route, RouteStatus, Base, Account, SpareProxy, RouteAction, ActionParams
from core.txt_manager import AccountData
from core import config
from core.logger import get_logger
from core.init_settings import settings


class DatabaseManager:
    def __init__(self, db_path: str = config.DATABASE, debug = settings.logging.debug_logging):
        self.db_path = Path(db_path)
        self.engine = create_engine(f'sqlite:///{db_path}',
                                    pool_size=100,  # Максимальное количество одновременных соединений
                                    max_overflow=0, # Дополнительные соединения сверх pool_size
                                    # echo=debug
                                    )
        self.Session = sessionmaker(bind=self.engine)
        self.conn = self.engine.connect()
        self.logger = get_logger(class_name=self.__class__.__name__)
        self.__debug = debug


    def init_db(self):
        """Создает все таблицы"""
        Base.metadata.create_all(self.engine)

    def add_accounts(self, accounts: list[AccountData], spare_proxies: list[str]):
        """Загружает аккаунты и прокси в базу"""
        if self.__debug:
            self.logger.info(f"Starting to add {len(accounts)} accounts to database")

        # Убеждаемся, что таблицы созданы
        if not self.engine.dialect.has_table(self.conn, 'accounts'):
            if self.__debug:
                self.logger.info("Creating database tables...")
            self.init_db()

        session = self.Session()
        try:
            # Добавляем аккаунты
            for account_data in accounts:
                if self.__debug:
                    self.logger.debug(f"Adding account {account_data.name}")

                account = Account(**asdict(account_data))
                session.add(account)

            # Сохраняем запасные прокси
            for proxy in spare_proxies:
                if self.__debug:
                    self.logger.debug(f"Adding spare proxy {proxy}")
                spare_proxy = SpareProxy(proxy=proxy)
                session.add(spare_proxy)

            session.commit()
            if self.__debug:
                self.logger.success(f"Successfully added {len(accounts)} accounts to database")

            # Проверяем что аккаунты действительно добавились
            count = session.query(Account).count()
            self.logger.info(f"Total accounts in database: {count}")

        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding accounts to database: {e}")
            raise
        finally:
            session.close()

    def get_routes_by_statuses(self, route_statuses: list[RouteStatus]) -> list[Type[Route]]:
        """Получает все маршруты c определенным статусом"""
        session = self.Session()
        try:
            # Используем joinedload для загрузки связанных actions вместе с маршрутами
            return session.query(Route).options(
                joinedload(Route.actions)
            ).filter(
                Route.status.in_(route_statuses)
            ).all()
        finally:
            session.close()

    def get_routes_by_statuses_paginated(self, statuses: list[RouteStatus], limit: int = 20, offset: int = 0) -> list[Route]:
        """
        Получает маршруты с указанными статусами с поддержкой пагинации.

        Args:
            statuses: Список статусов маршрутов для фильтрации
            limit: Максимальное количество возвращаемых маршрутов
            offset: Смещение (количество пропускаемых маршрутов)

        Returns:
            Список объектов Route с указанными статусами, ограниченный параметрами пагинации
        """
        session = self.Session()

        try:
            self.logger.debug(f"getting paginated routes")
            query = session.query(Route).options(
                joinedload(Route.actions)  # Предварительно загружаем actions
            ).filter(
                RouteAction.status.in_(statuses)
            )

            # Применяем пагинацию
            query = query.order_by(Route.account_id)  # Сортировка для стабильной пагинации # completed_at.desc()
            query = query.limit(limit).offset(offset)

            # Выполняем запрос и возвращаем результаты
            routes = query.all()

            return routes
        except Exception as e:
            self.logger.exception(f"Ошибка при получении маршрутов с пагинацией: {e}")
            return []
        finally:
            session.close()

    def get_routes_count_by_statuses(self, statuses: list[RouteStatus]) -> int:
        """
        Возвращает общее количество маршрутов с указанными статусами.

        Args:
            statuses: Список статусов маршрутов для фильтрации

        Returns:
            Общее количество маршрутов с указанными статусами
        """
        session = self.Session()
        try:
            count = session.query(func.count(Route.id.distinct())).join(Route.actions).filter(
                RouteAction.status.in_(statuses)
            ).scalar()
            return count
        except Exception as e:
            self.logger.error(f"Ошибка при получении количества маршрутов: {e}")
            return 0
        finally:
            session.close()

    def get_route_actions_filtered_by_statuses_paginated(self, statuses: list[RouteStatus],
                                                         limit: int = 20, offset: int = 0) -> list[RouteAction]:
        session = self.Session()
        try:
            query = session.query(RouteAction).join(Route).join(Account).options(
                joinedload(RouteAction.route).joinedload(Route.account),
                joinedload(RouteAction.route).joinedload(Route.actions)
            ).filter(
                RouteAction.status.in_(statuses)
            ).order_by(Account.id).limit(limit).offset(offset)

            # Выполняем запрос и возвращаем результаты
            route_actions = query.all()

            return route_actions
        except Exception as e:
            self.logger.exception(f"Ошибка при получении RouteAction с пагинацией: {e}")
            return []
        finally:
            session.close()


    @staticmethod
    def _shuffle_order_indexes(action_list: list[RouteAction]):
        indexes = [action.order_index for action in action_list]
        random.shuffle(indexes)
        for action in action_list:
            action.order_index = indexes.pop()
        return action_list

    def create_or_update_action_params(self, action_params_json):
        session = self.Session()
        try:
            # Сначала проверяем, существует ли уже такой параметр
            existing = session.query(ActionParams).filter_by(action_params=action_params_json).first()

            if existing:
                existing.updated_at = datetime.now()
                result = existing
            else:
                new_params = ActionParams(
                    action_params=action_params_json,
                    created_at=datetime.now()
                )
                session.add(new_params)
                result = new_params

            session.commit()
            return result
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def generate_routes_for_accounts(self, preset_data: dict[str, dict]):
        """Создает маршрут для каждого аккаунта, если у него еще нет маршрута"""
        if self.__debug:
            self.logger.info("Starting route generation")

        session = self.Session()
        try:
            # Проверяем текущее состояние базы
            routes_before = session.query(Route).count()
            actions_before = session.query(RouteAction).count()
            if self.__debug:
                self.logger.info(f"Before generation: {routes_before} routes, {actions_before} actions")

            # Получаем аккаунты с их текущими маршрутами
            accounts = session.query(Account).options(joinedload(Account.route)).all()
            if self.__debug:
                self.logger.info(f"Found {len(accounts)} accounts in database")

            self.logger.debug(f"functions_params {preset_data['functions_params']}")
            action_params_str = json.dumps(preset_data["functions_params"])
            action_params_obj = self.create_or_update_action_params(action_params_str)
            # action_params_obj = ActionParams()
            # action_params_obj.action_params = action_params_str
            # session.add(action_params_obj)

            for account in accounts:
                try:
                    # Проверяем, есть ли уже маршрут у аккаунта
                    if account.route:
                        self.logger.warning(f"Account {str(account.name)} already has route {account.route.id}, skipping")
                        continue
                    if self.__debug:
                        self.logger.debug(f"Creating route for account {str(account.name)}")

                    # Создаем новый маршрут для аккаунта
                    route = Route()
                    session.add(route)
                    account.route = route  # Устанавливаем связь с аккаунтом

                    # Создаем действия для маршрута
                    for index, (action_type, action_name) in enumerate(preset_data["functions"].items()):
                        if self.__debug:
                            self.logger.debug(f"Adding action {action_name} to route")

                        if preset_data.get("repeat_actions") and str(action_type) in preset_data["repeat_actions"]:
                            repeat_data = preset_data["repeat_actions"][str(action_type)]
                            repeat_num = random.randint(repeat_data[0], repeat_data[1])
                            for _ in range(repeat_num):
                                route_action = RouteAction(
                                    action_type=str(action_type),
                                    action_name=str(action_name),
                                    order_index=index  # Устанавливаем порядковый индекс
                                )
                                route_action.action_params = action_params_obj
                                session.add(route_action)
                                route.actions.append(route_action)

                        else:
                            route_action = RouteAction(
                                action_type=str(action_type),
                                action_name=str(action_name),
                                order_index=index  # Устанавливаем порядковый индекс
                            )
                            route_action.action_params = action_params_obj
                            session.add(route_action)
                            route.actions.append(route_action)

                    if settings.general.SHUFFLE_ACTIONS:
                        shuffled_actions = [action_ for action_ in route.actions]
                        shuffled_actions = self._shuffle_order_indexes(shuffled_actions)

                        route.actions = shuffled_actions

                    session.flush()  # Применяем изменения для проверки
                    if self.__debug:
                        self.logger.success(f"Created route {route.id} with {len(route.actions)} actions for account {account.name}")

                except Exception as e:
                    self.logger.exception(f"{e.__class__.__name__} Error creating route for account {str(account.name)}: {str(e)}")
                    continue

            # Проверяем финальное состояние
            routes_after = session.query(Route).count()

            actions_after = session.query(RouteAction).count()
            if self.__debug:
                self.logger.info(f"After generation: {routes_after} routes (+{routes_after - routes_before}), "
                           f"{actions_after} actions (+{actions_after - actions_before})")

            session.commit()
            self.logger.success("Successfully generated all routes")

        except Exception as e:
            session.rollback()
            self.logger.error(f"Error in generate_routes_for_accounts: {e}")
            raise
        finally:
            session.close()

    def flush_routes(self):
        """Удаляет все маршруты и их действия"""
        session = self.Session()
        try:
            # Проверяем количество записей до удаления
            routes_before = session.query(Route).count()
            actions_before = session.query(RouteAction).count()
            if self.__debug:
                self.logger.info(f"Before deletion: {routes_before} routes, {actions_before} actions")

            # Получаем все маршруты с их действиями
            routes = session.query(Route).options(joinedload(Route.actions)).all()
            if self.__debug:
                self.logger.info(f"Found {len(routes)} routes to delete")

            for route in routes:
                if self.__debug:
                    self.logger.info(f"Deleting route {route.id} with {len(route.actions)} actions")
                session.delete(route)

            session.flush()  # Применяем изменения, но не коммитим

            # Проверяем количество записей после удаления
            routes_after = session.query(Route).count()
            actions_after = session.query(RouteAction).count()
            if self.__debug:
                self.logger.info(f"After deletion: {routes_after} routes, {actions_after} actions")

            if actions_after > 0:
                # Если действия остались, удаляем их явно
                if self.__debug:
                    self.logger.warning("Actions still exist, deleting them manually")
                session.query(RouteAction).delete()

            session.commit()

            # Финальная проверка после коммита
            final_routes = session.query(Route).count()
            final_actions = session.query(RouteAction).count()
            if self.__debug:
                self.logger.info(f"Final count: {final_routes} routes, {final_actions} actions")

        except Exception as e:
            session.rollback()
            self.logger.error(f"Error deleting routes: {e}")
            raise
        finally:
            session.close()

    def delete_all_routes(self):
        """Удаляет все маршруты из базы данных"""
        session = self.Session()

        # Убеждаемся, что таблицы созданы
        if not self.engine.dialect.has_table(self.conn, 'accounts'):
            self.logger.info(f"Database not found, creating tables...")
            self.init_db()
            self.logger.success(f"Created database")
            return

        try:
            self.flush_routes()

            session.query(Account).delete()
            session.query(SpareProxy).delete()
            session.commit()
            self.logger.success("Successfully flushed all routes")
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error flushing routes: {e}")
            raise
        finally:
            session.close()

    async def update_obj_column(self, obj: Account | Route | RouteAction,
                                         attribute: str, update_info) -> Account | Route | RouteAction:
        session = self.Session()
        try:
            # Получаем свежую версию объекта из базы
            refreshed_obj = session.merge(obj)

            if hasattr(refreshed_obj, attribute):
                setattr(refreshed_obj, attribute, update_info)
                setattr(obj, attribute, update_info)

                if hasattr(refreshed_obj, 'updated_at'):
                    refreshed_obj.updated_at = datetime.now()

                session.commit()

                # Если есть updated_at, обновляем и его
                if hasattr(obj, 'updated_at') and hasattr(refreshed_obj, 'updated_at'):
                    obj.updated_at = refreshed_obj.updated_at

                return obj

            else:
                self.logger.critical(f"No {attribute} attribute in {obj}")

        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

    async def get_obj_column_value(self, obj: Account | Route | RouteAction, column: str):
        session = self.Session()
        try:
            # Получаем свежую версию объекта из базы
            refreshed_obj = session.merge(obj)

            if hasattr(refreshed_obj, column):
                return getattr(obj, column)

            else:
                self.logger.critical(f"No {column} attribute in {obj}")

        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

    def get_accounts(self, session: Session | None = None) -> list[type[Account]] | list[Account]:
        if session:
            return session.query(Account).all()
        return self.all(entities=Account)

    def get_account_by_pk(self, private_key: str) -> Account | None:
        return self.one(Account, Account.private_key == private_key)

    def get_account_by_id(self, account_id: int) -> Account | None:
        return self.one(Account, Account.id == account_id)

    def get_spare_proxy(self):
        return self.one(SpareProxy, SpareProxy.is_used == False)

    def get_pending_action(self):
        return self.one(RouteAction, RouteAction.status == RouteStatus.PENDING)

    def get_in_progress_action(self):
        return self.one(RouteAction, RouteAction.status == RouteStatus.IN_PROGRESS)

    def get_completed_action(self):
        return self.one(RouteAction, RouteAction.status == RouteStatus.COMPLETED)

    def get_failed_action(self):
        return self.one(RouteAction, RouteAction.status == RouteStatus.FAILED)

    def add(self, obj):
        session = self.Session()
        session.add(obj)

    def merge(self, obj):
        session = self.Session()
        session.merge(obj)

    def all(self, entities=None, *criterion, stmt=None) -> list:
        """
        Fetches all rows.

        :param entities: an ORM entity
        :param stmt: stmt
        :param criterion: criterion for rows filtering
        :return list: the list of rows
        """
        session = self.Session()

        if stmt is not None:
            return list(session.scalars(stmt).all())

        if entities and criterion:
            return session.query(entities).filter(*criterion).all()

        if entities:
            return session.query(entities).all()

        return []

    def one(self, entities=None, *criterion, stmt=None, from_the_end: bool = False):
        """
        Fetches one row.

        :param entities: an ORM entity
        :param stmt: stmt
        :param criterion: criterion for rows filtering
        :param from_the_end: get the row from the end
        :return list: found row or None
        """
        if entities and criterion:
            rows = self.all(entities, *criterion)
        else:
            rows = self.all(stmt=stmt)

        if rows:
            if from_the_end:
                return rows[-1]

            return rows[0]

        return None

    def execute(self, query, *args):
        """
        Executes SQL query.

        :param query: the query
        :param args: any additional arguments
        """
        result = self.conn.execute(text(query), *args)
        self.commit()
        return result

    def commit(self):
        """
        Commits changes.
        """
        session = self.Session()
        try:
            session.commit()
        except DatabaseError:
            session.rollback()

    def insert(self, row: object | list[object]):
        """
        Inserts rows.

        :param Union[object, list[object]] row: an ORM entity or list of entities
        """
        session = self.Session()
        if isinstance(row, list):
            session.add_all(row)
        elif isinstance(row, object):
            session.add(row)
        else:
            raise ValueError('Wrong type!')
        session.commit()

    def update(self, entities, columns: object | list[object], now_value, future_value, *args):
        """
        Updates specified columns with args

        :param entities: specify which table needs to be updated
        :param Union[object, list[object]] columns: columns which values have to be changed
        :param args: any additional arguments
        :param now_value
        :param future_value
        """
        session = self.Session()
        if isinstance(columns, list):
            for column in columns:
                stmt = update(table=entities).where(column == now_value).values(future_value)
                session.query(stmt)

            # self.s.add_all(columns)
            # update(table=self.s.add_all(columns))
            # update(columns)

        elif isinstance(columns, object):
            stmt = update(table=entities).where(columns == now_value).values(future_value)
            session.query(stmt)

        else:
            raise ValueError('Wrong entities type or smth')

        # stmt = (
        #     update(table=entities).filter(columns).values()
        #
        # )
        session.commit()

    def delete(self, row: object):
        """
        Updates specified columns with args

        :param row: an ORM entity
        """
        session = self.Session()

        session.delete(row)
        session.commit()

    def get_free_proxy(self) -> str | None:
        """Получает свободный прокси из запасных"""
        session = self.Session()
        try:
            proxy = session.query(SpareProxy).filter_by(in_use=False).first()
            if proxy:
                proxy.in_use = True
                session.commit()
                return proxy.proxy
            return None
        finally:
            session.close()

    def reset_proxies(self):
        session = self.Session()
        try:
            # Update all SpareProxy records to set in_use=False
            session.query(SpareProxy).update({SpareProxy.in_use: False})
            session.commit()
            self.logger.info("Reset all SpareProxy records to in_use=False")
        finally:
            session.close()

    def release_proxy(self, proxy_str: str) -> None:
        """Освобождает прокси"""
        session = self.Session()
        try:
            proxy = session.query(SpareProxy).filter_by(proxy=proxy_str).first()
            if proxy:
                proxy.in_use = False
                session.commit()
        finally:
            session.close()

    def get_routes_with_actions_by_status_paginated(self, statuses: list[RouteStatus], 
                                                   limit: int = 20, offset: int = 0) -> list[Route]:
        """
        Получает маршруты с предзагруженными действиями и аккаунтами для отображения.
        Возвращает уникальные маршруты, у которых есть действия с указанными статусами.
        """
        session = self.Session()
        try:
            # Получаем уникальные маршруты, у которых есть действия с нужными статусами
            query = session.query(Route).join(RouteAction).filter(
                RouteAction.status.in_(statuses)
            ).options(
                joinedload(Route.account),
                joinedload(Route.actions)
            ).distinct().order_by(Route.account_id).limit(limit).offset(offset)

            routes = query.all()
            return routes
        except Exception as e:
            self.logger.exception(f"Ошибка при получении маршрутов с действиями: {e}")
            return []
        finally:
            session.close()

    def get_action_params(self):
        session = self.Session()
        try:
            action_params = session.query(ActionParams).first()
            if action_params:
                return action_params
            return None
        finally:
            session.close()

db = DatabaseManager()

if __name__ == "__main__":
    obj = db.execute(f"SELECT created_at FROM Routes WHERE account_id == 1")
    print(f"obj: {obj.scalar()}")
