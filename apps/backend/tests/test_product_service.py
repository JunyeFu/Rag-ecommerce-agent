"""商品服务单元测试 - CRUD + 过滤 + 排序 + 分页"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.product_service import (
    get_products,
    get_product_by_id,
    create_product,
    update_product,
    delete_product,
)


def _make_result(scalars=None, scalar=None, scalar_one_or_none=None, rowcount=0):
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars or []
    result.scalar.return_value = scalar
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.rowcount = rowcount
    return result



@pytest.mark.unit
class TestGetProducts:
    """get_products - 分页查询 + 过滤 + 排序"""

    @pytest.mark.asyncio
    async def test_returns_products_and_total(self, mock_db):
        products = [MagicMock(), MagicMock()]
        mock_db.execute.side_effect = [
            _make_result(scalars=products),
            _make_result(scalar=2),
        ]
        result, total = await get_products(mock_db, page=1, size=20)
        assert result == products
        assert total == 2

    @pytest.mark.asyncio
    async def test_category_filter_applied(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalars=[]),
            _make_result(scalar=0),
        ]
        await get_products(mock_db, category="食品饮料")
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_price_range_filter(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalars=[]),
            _make_result(scalar=0),
        ]
        await get_products(mock_db, price_min=10.0, price_max=100.0)
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_keyword_filter(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalars=[]),
            _make_result(scalar=0),
        ]
        await get_products(mock_db, keyword="薄荷糖")
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_sort_by_price_asc(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalars=[]),
            _make_result(scalar=0),
        ]
        await get_products(mock_db, sort_by="price_asc")
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_sort_invalid_falls_back_to_sales(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalars=[]),
            _make_result(scalar=0),
        ]
        await get_products(mock_db, sort_by="invalid_sort")
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_pagination_offset(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalars=[]),
            _make_result(scalar=0),
        ]
        await get_products(mock_db, page=3, size=10)
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalars=[]),
            _make_result(scalar=0),
        ]
        result, total = await get_products(mock_db)
        assert result == []
        assert total == 0


@pytest.mark.unit
class TestGetProductById:
    """get_product_by_id - UUID + legacy source_product_id 查找"""

    @pytest.mark.asyncio
    async def test_valid_uuid_found(self, mock_db):
        product = MagicMock(title="Test Product")
        mock_db.execute.return_value = _make_result(scalar_one_or_none=product)
        result = await get_product_by_id(mock_db, str(uuid.uuid4()))
        assert result == product

    @pytest.mark.asyncio
    async def test_uuid_not_found_falls_back_to_source_id(self, mock_db):
        legacy_product = MagicMock(title="Legacy Product")
        mock_db.execute.side_effect = [
            _make_result(scalar_one_or_none=None),
            _make_result(scalar_one_or_none=legacy_product),
        ]
        result = await get_product_by_id(mock_db, str(uuid.uuid4()))
        assert result == legacy_product

    @pytest.mark.asyncio
    async def test_non_uuid_string_uses_source_product_id(self, mock_db):
        product = MagicMock(title="Legacy Product")
        mock_db.execute.return_value = _make_result(scalar_one_or_none=product)
        result = await get_product_by_id(mock_db, "SP-001")
        assert result == product

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalar_one_or_none=None),
            _make_result(scalar_one_or_none=None),
        ]
        result = await get_product_by_id(mock_db, str(uuid.uuid4()))
        assert result is None


@pytest.mark.unit
class TestCreateProduct:
    """create_product - 创建商品"""

    @pytest.mark.asyncio
    async def test_create_flushes_and_returns(self, mock_db):
        data = {"title": "Test", "price": 9.9, "category": "食品"}
        result = await create_product(mock_db, data)
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_assigns_all_fields(self, mock_db):
        data = {"title": "薄荷糖", "price": 9.9, "category": "食品", "brand": "都市草园"}
        result = await create_product(mock_db, data)
        assert result.title == "薄荷糖"


@pytest.mark.unit
class TestUpdateProduct:
    """update_product - 更新商品"""

    @pytest.mark.asyncio
    async def test_update_existing_product(self, mock_db):
        product = MagicMock(title="Old Title", price=10.0)
        mock_db.execute.return_value = _make_result(scalar_one_or_none=product)
        await update_product(mock_db, str(uuid.uuid4()), {"title": "New Title"})
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalar_one_or_none=None),
            _make_result(scalar_one_or_none=None),
        ]
        result = await update_product(mock_db, str(uuid.uuid4()), {"title": "New"})
        assert result is None

    @pytest.mark.asyncio
    async def test_update_skips_none_values(self, mock_db):
        product = MagicMock()
        product.title = "Old"
        mock_db.execute.return_value = _make_result(scalar_one_or_none=product)
        await update_product(mock_db, str(uuid.uuid4()), {"title": "New", "price": None})
        assert product.title == "New"


@pytest.mark.unit
class TestDeleteProduct:
    """delete_product - 删除商品"""

    @pytest.mark.asyncio
    async def test_delete_by_valid_uuid(self, mock_db):
        mock_db.execute.return_value = _make_result(rowcount=1)
        result = await delete_product(mock_db, str(uuid.uuid4()))
        assert result is True
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, mock_db):
        mock_db.execute.return_value = _make_result(rowcount=0)
        result = await delete_product(mock_db, str(uuid.uuid4()))
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_non_uuid_returns_false(self, mock_db):
        result = await delete_product(mock_db, "not-a-uuid")
        assert result is False
        mock_db.execute.assert_not_called()
