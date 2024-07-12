# Licensed to Modin Development Team under one or more contributor license agreements.
# See the NOTICE file distributed with this work for additional information regarding
# copyright ownership.  The Modin Development Team licenses this file to you under the
# Apache License, Version 2.0 (the "License"); you may not use this file except in
# compliance with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific language
# governing permissions and limitations under the License.
from itertools import product

import matplotlib
import numpy as np
import pandas
import pytest

import modin.pandas as pd
from modin.config import MinRowPartitionSize, NativeDataframeMode, NPartitions
from modin.pandas.testing import assert_index_equal
from modin.tests.pandas.utils import (
    RAND_HIGH,
    RAND_LOW,
    create_test_dfs,
    create_test_series,
    default_to_pandas_ignore_string,
    df_equals,
    eval_general,
    eval_general_interop,
    test_data,
    test_data_keys,
    test_data_values,
)

NPartitions.put(4)

# Force matplotlib to not use any Xwindows backend.
matplotlib.use("Agg")

# Our configuration in pytest.ini requires that we explicitly catch all
# instances of defaulting to pandas, but some test modules, like this one,
# have too many such instances.
# TODO(https://github.com/modin-project/modin/issues/3655): catch all instances
# of defaulting to pandas.
pytestmark = pytest.mark.filterwarnings(default_to_pandas_ignore_string)


def eval_setitem(md_df, pd_df, value, col=None, loc=None, expected_exception=None):
    if loc is not None:
        col = pd_df.columns[loc]

    value_getter = value if callable(value) else (lambda *args, **kwargs: value)

    eval_general(
        md_df,
        pd_df,
        lambda df: df.__setitem__(col, value_getter(df)),
        __inplace__=True,
        expected_exception=expected_exception,
    )
    data_frame_mode_pair_list = list(product(NativeDataframeMode.choices, repeat=2))
    for data_frame_mode_pair in data_frame_mode_pair_list:
        eval_general_interop(
            pd_df,
            None,
            lambda df1, df2: df1.__setitem__(col, value_getter(df2)),
            data_frame_mode_pair,
            __inplace__=True,
            expected_exception=expected_exception,
        )


def eval_loc(md_df, pd_df, value, key):
    if isinstance(value, tuple):
        assert len(value) == 2
        # case when value for pandas different
        md_value, pd_value = value
    else:
        md_value, pd_value = value, value

    eval_general(
        md_df,
        pd_df,
        lambda df: df.loc.__setitem__(
            key, pd_value if isinstance(df, pandas.DataFrame) else md_value
        ),
        __inplace__=True,
    )


@pytest.mark.parametrize("data", test_data_values, ids=test_data_keys)
@pytest.mark.parametrize(
    "key_func",
    [
        # test for the case from https://github.com/modin-project/modin/issues/4308
        lambda df: "non_existing_column",
        lambda df: df.columns[0],
        lambda df: df.index,
        lambda df: [df.index, df.columns[0]],
        lambda df: (
            pandas.Series(list(range(len(df.index))))
            if isinstance(df, pandas.DataFrame)
            else pd.Series(list(range(len(df))))
        ),
    ],
    ids=[
        "non_existing_column",
        "first_column_name",
        "original_index",
        "list_of_index_and_first_column_name",
        "series_of_integers",
    ],
)
@pytest.mark.parametrize(
    "drop_kwargs",
    [{"drop": True}, {"drop": False}, {}],
    ids=["drop_True", "drop_False", "no_drop_param"],
)
@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test_set_index(data, key_func, drop_kwargs, request, data_frame_mode_pair):
    if (
        "list_of_index_and_first_column_name" in request.node.name
        and "drop_False" in request.node.name
    ):
        pytest.xfail(
            reason="KeyError: https://github.com/modin-project/modin/issues/5636"
        )
    expected_exception = None
    if "non_existing_column" in request.node.callspec.id:
        expected_exception = KeyError(
            "None of ['non_existing_column'] are in the columns"
        )

    eval_general_interop(
        data,
        None,
        lambda df1, df2: df1.set_index(key_func(df2), **drop_kwargs),
        expected_exception=expected_exception,
        data_frame_mode_pair=data_frame_mode_pair,
    )


@pytest.mark.parametrize("data", test_data_values, ids=test_data_keys)
@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test_loc(data, data_frame_mode_pair):
    modin_df = pd.DataFrame(data)
    pandas_df = pandas.DataFrame(data)
    modin_df, pandas_df = create_test_dfs(data, data_frame_mode=data_frame_mode_pair[0])

    indices = [i % 3 == 0 for i in range(len(modin_df.index))]
    columns = [i % 5 == 0 for i in range(len(modin_df.columns))]

    # Key is a Modin or pandas series of booleans
    series1, _ = create_test_series(indices, data_frame_mode=data_frame_mode_pair[0])
    series2, _ = create_test_series(
        columns, index=modin_df.columns, data_frame_mode=data_frame_mode_pair[0]
    )
    df_equals(
        modin_df.loc[series1, series2],
        pandas_df.loc[
            pandas.Series(indices), pandas.Series(columns, index=modin_df.columns)
        ],
    )


@pytest.mark.parametrize("left, right", [(2, 1), (6, 1), (lambda df: 70, 1), (90, 70)])
@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test_loc_insert_row(left, right, data_frame_mode_pair):
    # This test case comes from
    # https://github.com/modin-project/modin/issues/3764
    data = [[1, 2, 3], [4, 5, 6]]

    def _test_loc_rows(df1, df2):
        df1.loc[left] = df2.loc[right]
        return df1

    expected_exception = None
    if right == 70:
        pytest.xfail(reason="https://github.com/modin-project/modin/issues/7024")

    eval_general_interop(
        data,
        None,
        _test_loc_rows,
        expected_exception=expected_exception,
        data_frame_mode_pair=data_frame_mode_pair,
    )


@pytest.fixture(params=list(product(NativeDataframeMode.choices, repeat=2)))
def loc_iter_dfs_interop(request):
    data_frame_mode_pair = request.param
    columns = ["col1", "col2", "col3"]
    index = ["row1", "row2", "row3"]
    md_df1, pd_df1 = create_test_dfs(
        {col: ([idx] * len(index)) for idx, col in enumerate(columns)},
        columns=columns,
        index=index,
        data_frame_mode=data_frame_mode_pair[0],
    )
    md_df2, pd_df2 = create_test_dfs(
        {col: ([idx] * len(index)) for idx, col in enumerate(columns)},
        columns=columns,
        index=index,
        data_frame_mode=data_frame_mode_pair[1],
    )
    return md_df1, pd_df1, md_df2, pd_df2


@pytest.mark.parametrize("reverse_order", [False, True])
@pytest.mark.parametrize("axis", [0, 1])
def test_loc_iter_assignment(loc_iter_dfs_interop, reverse_order, axis):
    if reverse_order and axis:
        pytest.xfail(
            "Due to internal sorting of lookup values assignment order is lost, see GH-#2552"
        )

    md_df1, pd_df1, md_df2, pd_df2 = loc_iter_dfs_interop

    select = [slice(None), slice(None)]
    select[axis] = sorted(pd_df1.axes[axis][:-1], reverse=reverse_order)
    select = tuple(select)

    pd_df1.loc[select] = pd_df1.loc[select] + pd_df2.loc[select]
    md_df1.loc[select] = md_df1.loc[select] + md_df2.loc[select]
    df_equals(md_df1, pd_df1)


@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test_loc_series(data_frame_mode_pair):
    md_df1, pd_df1 = create_test_dfs(
        {"a": [1, 2], "b": [3, 4]}, data_frame_mode=data_frame_mode_pair[0]
    )
    md_df2, pd_df2 = create_test_dfs(
        {"a": [1, 2], "b": [3, 4]}, data_frame_mode=data_frame_mode_pair[1]
    )

    pd_df1.loc[pd_df2["a"] > 1, "b"] = np.log(pd_df1["b"])
    md_df1.loc[md_df2["a"] > 1, "b"] = np.log(md_df1["b"])

    df_equals(pd_df1, md_df1)


@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test_reindex_like(data_frame_mode_pair):
    o_data = [
        [24.3, 75.7, "high"],
        [31, 87.8, "high"],
        [22, 71.6, "medium"],
        [35, 95, "medium"],
    ]
    o_columns = ["temp_celsius", "temp_fahrenheit", "windspeed"]
    o_index = pd.date_range(start="2014-02-12", end="2014-02-15", freq="D")
    new_data = [[28, "low"], [30, "low"], [35.1, "medium"]]
    new_columns = ["temp_celsius", "windspeed"]
    new_index = pd.DatetimeIndex(["2014-02-12", "2014-02-13", "2014-02-15"])
    modin_df1, pandas_df1 = create_test_dfs(
        o_data,
        columns=o_columns,
        index=o_index,
        data_frame_mode=data_frame_mode_pair[0],
    )
    modin_df2, pandas_df2 = create_test_dfs(
        new_data,
        columns=new_columns,
        index=new_index,
        data_frame_mode=data_frame_mode_pair[1],
    )
    modin_result = modin_df2.reindex_like(modin_df1)
    pandas_result = pandas_df2.reindex_like(pandas_df1)
    df_equals(modin_result, pandas_result)


@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test_reindex_multiindex(data_frame_mode_pair):
    data1, data2 = np.random.randint(1, 20, (5, 5)), np.random.randint(10, 25, 6)
    index = np.array(["AUD", "BRL", "CAD", "EUR", "INR"])
    pandas_midx = pandas.MultiIndex.from_product(
        [["Bank_1", "Bank_2"], ["AUD", "CAD", "EUR"]], names=["Bank", "Curency"]
    )
    modin_df1, pandas_df1 = create_test_dfs(
        data=data1, index=index, columns=index, data_frame_mode=data_frame_mode_pair[0]
    )
    modin_df2, pandas_df2 = create_test_dfs(
        data=data2, index=pandas_midx, data_frame_mode=data_frame_mode_pair[1]
    )

    modin_df2.columns, pandas_df2.columns = ["Notional"], ["Notional"]
    md_midx = pd.MultiIndex.from_product([modin_df2.index.levels[0], modin_df1.index])
    pd_midx = pandas.MultiIndex.from_product(
        [pandas_df2.index.levels[0], pandas_df1.index]
    )
    # reindex without axis, index, or columns
    modin_result = modin_df1.reindex(md_midx, fill_value=0)
    pandas_result = pandas_df1.reindex(pd_midx, fill_value=0)
    df_equals(modin_result, pandas_result)
    # reindex with only axis
    modin_result = modin_df1.reindex(md_midx, fill_value=0, axis=0)
    pandas_result = pandas_df1.reindex(pd_midx, fill_value=0, axis=0)
    df_equals(modin_result, pandas_result)
    # reindex with axis and level
    modin_result = modin_df1.reindex(md_midx, fill_value=0, axis=0, level=0)
    pandas_result = pandas_df1.reindex(pd_midx, fill_value=0, axis=0, level=0)
    df_equals(modin_result, pandas_result)


@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test_getitem_empty_mask(data_frame_mode_pair):
    # modin-project/modin#517
    modin_frames = []
    pandas_frames = []
    data1 = np.random.randint(0, 100, size=(100, 4))
    mdf1, pdf1 = create_test_dfs(
        data1, columns=list("ABCD"), data_frame_mode=data_frame_mode_pair[0]
    )

    modin_frames.append(mdf1)
    pandas_frames.append(pdf1)

    data2 = np.random.randint(0, 100, size=(100, 4))
    mdf2, pdf2 = create_test_dfs(
        data2, columns=list("ABCD"), data_frame_mode=data_frame_mode_pair[1]
    )
    modin_frames.append(mdf2)
    pandas_frames.append(pdf2)

    data3 = np.random.randint(0, 100, size=(100, 4))
    mdf3, pdf3 = create_test_dfs(
        data3, columns=list("ABCD"), data_frame_mode=data_frame_mode_pair[0]
    )
    modin_frames.append(mdf3)
    pandas_frames.append(pdf3)

    modin_data = pd.concat(modin_frames)
    pandas_data = pandas.concat(pandas_frames)
    df_equals(
        modin_data[[False for _ in modin_data.index]],
        pandas_data[[False for _ in modin_data.index]],
    )


@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test___setitem__mask(data_frame_mode_pair):
    # DataFrame mask:
    data = test_data["int_data"]
    modin_df1, pandas_df1 = create_test_dfs(
        data, data_frame_mode=data_frame_mode_pair[0]
    )
    modin_df2, pandas_df2 = create_test_dfs(
        data, data_frame_mode=data_frame_mode_pair[0]
    )

    mean = int((RAND_HIGH + RAND_LOW) / 2)
    pandas_df1[pandas_df2 > mean] = -50
    modin_df1[modin_df2 > mean] = -50

    df_equals(modin_df1, pandas_df1)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"id": [], "max_speed": [], "health": []},
        {"id": [1], "max_speed": [2], "health": [3]},
        {"id": [4, 40, 400], "max_speed": [111, 222, 333], "health": [33, 22, 11]},
    ],
    ids=["empty_frame", "empty_cols", "1_length_cols", "2_length_cols"],
)
@pytest.mark.parametrize(
    "value",
    [[11, 22], [11, 22, 33]],
    ids=["2_length_val", "3_length_val"],
)
@pytest.mark.parametrize("convert_to_series", [False, True])
@pytest.mark.parametrize("new_col_id", [123, "new_col"], ids=["integer", "string"])
@pytest.mark.parametrize(
    "data_frame_mode_pair", list(product(NativeDataframeMode.choices, repeat=2))
)
def test_setitem_on_empty_df(
    data, value, convert_to_series, new_col_id, data_frame_mode_pair
):
    modin_df, pandas_df = create_test_dfs(data, data_frame_mode=data_frame_mode_pair[0])

    def applyier(df):
        if convert_to_series:
            converted_value = (
                pandas.Series(value)
                if isinstance(df, pandas.DataFrame)
                else create_test_series(value, data_frame_mode=data_frame_mode_pair[1])[
                    1
                ]
            )
        else:
            converted_value = value
        df[new_col_id] = converted_value
        return df

    expected_exception = None
    if not convert_to_series:
        values_length = len(value)
        index_length = len(pandas_df.index)
        expected_exception = ValueError(
            f"Length of values ({values_length}) does not match length of index ({index_length})"
        )

    eval_general(
        modin_df,
        pandas_df,
        applyier,
        # https://github.com/modin-project/modin/issues/5961
        comparator_kwargs={
            "check_dtypes": not (len(pandas_df) == 0 and len(pandas_df.columns) != 0)
        },
        expected_exception=expected_exception,
    )


def test_setitem_on_empty_df_4407():
    data = {}
    index = pd.date_range(end="1/1/2018", periods=0, freq="D")
    column = pd.date_range(end="1/1/2018", periods=1, freq="h")[0]
    modin_df = pd.DataFrame(data, columns=index)
    pandas_df = pandas.DataFrame(data, columns=index)

    modin_df[column] = pd.Series([1])
    pandas_df[column] = pandas.Series([1])

    df_equals(modin_df, pandas_df)
    assert modin_df.columns.freq == pandas_df.columns.freq


def test___setitem__unhashable_list():
    # from #3258 and #3291
    cols = ["a", "b"]
    modin_df = pd.DataFrame([[0, 0]], columns=cols)
    modin_df[cols] = modin_df[cols]
    pandas_df = pandas.DataFrame([[0, 0]], columns=cols)
    pandas_df[cols] = pandas_df[cols]
    df_equals(modin_df, pandas_df)


def test_setitem_unhashable_key():
    source_modin_df, source_pandas_df = create_test_dfs(test_data["float_nan_data"])
    row_count = source_modin_df.shape[0]

    def _make_copy(df1, df2):
        return df1.copy(deep=True), df2.copy(deep=True)

    for key in (["col1", "col2"], ["new_col1", "new_col2"]):
        # 1d list case
        value = [1, 2]
        modin_df, pandas_df = _make_copy(source_modin_df, source_pandas_df)
        eval_setitem(modin_df, pandas_df, value, key)

        # 2d list case
        value = [[1, 2]] * row_count
        modin_df, pandas_df = _make_copy(source_modin_df, source_pandas_df)
        eval_setitem(modin_df, pandas_df, value, key)

        # pandas DataFrame case
        df_value = pandas.DataFrame(value, columns=["value_col1", "value_col2"])
        modin_df, pandas_df = _make_copy(source_modin_df, source_pandas_df)
        eval_setitem(modin_df, pandas_df, df_value, key)

        # numpy array case
        value = df_value.to_numpy()
        modin_df, pandas_df = _make_copy(source_modin_df, source_pandas_df)
        eval_setitem(modin_df, pandas_df, value, key)

        # pandas Series case
        value = df_value["value_col1"]
        modin_df, pandas_df = _make_copy(source_modin_df, source_pandas_df)
        eval_setitem(
            modin_df,
            pandas_df,
            value,
            key[:1],
            expected_exception=ValueError("Columns must be same length as key"),
        )

        # pandas Index case
        value = df_value.index
        modin_df, pandas_df = _make_copy(source_modin_df, source_pandas_df)
        eval_setitem(
            modin_df,
            pandas_df,
            value,
            key[:1],
            expected_exception=ValueError("Columns must be same length as key"),
        )

        # scalar case
        value = 3
        modin_df, pandas_df = _make_copy(source_modin_df, source_pandas_df)
        eval_setitem(modin_df, pandas_df, value, key)

        # test failed case: ValueError('Columns must be same length as key')
        eval_setitem(
            modin_df,
            pandas_df,
            df_value[["value_col1"]],
            key,
            expected_exception=ValueError("Columns must be same length as key"),
        )


def test_setitem_2d_insertion():
    def build_value_picker(modin_value, pandas_value):
        """Build a function that returns either Modin or pandas DataFrame depending on the passed frame."""
        return lambda source_df, *args, **kwargs: (
            modin_value
            if isinstance(source_df, (pd.DataFrame, pd.Series))
            else pandas_value
        )

    modin_df, pandas_df = create_test_dfs(test_data["int_data"])

    # Easy case - key and value.columns are equal
    modin_value, pandas_value = create_test_dfs(
        {"new_value1": np.arange(len(modin_df)), "new_value2": np.arange(len(modin_df))}
    )
    eval_setitem(
        modin_df,
        pandas_df,
        build_value_picker(modin_value, pandas_value),
        col=["new_value1", "new_value2"],
    )

    # Key and value.columns have equal values but in different order
    new_columns = ["new_value3", "new_value4"]
    modin_value.columns, pandas_value.columns = new_columns, new_columns
    eval_setitem(
        modin_df,
        pandas_df,
        build_value_picker(modin_value, pandas_value),
        col=["new_value4", "new_value3"],
    )

    # Key and value.columns have different values
    new_columns = ["new_value5", "new_value6"]
    modin_value.columns, pandas_value.columns = new_columns, new_columns
    eval_setitem(
        modin_df,
        pandas_df,
        build_value_picker(modin_value, pandas_value),
        col=["__new_value5", "__new_value6"],
    )

    # Key and value.columns have different lengths, testing that both raise the same exception
    eval_setitem(
        modin_df,
        pandas_df,
        build_value_picker(modin_value.iloc[:, [0]], pandas_value.iloc[:, [0]]),
        col=["new_value7", "new_value8"],
        expected_exception=ValueError("Columns must be same length as key"),
    )


@pytest.mark.parametrize("does_value_have_different_columns", [True, False])
def test_setitem_2d_update(does_value_have_different_columns):
    def test(dfs, iloc):
        """Update columns on the given numeric indices."""
        df1, df2 = dfs
        cols1 = df1.columns[iloc].tolist()
        cols2 = df2.columns[iloc].tolist()
        df1[cols1] = df2[cols2]
        return df1

    modin_df, pandas_df = create_test_dfs(test_data["int_data"])
    modin_df2, pandas_df2 = create_test_dfs(test_data["int_data"])
    modin_df2 *= 10
    pandas_df2 *= 10

    if does_value_have_different_columns:
        new_columns = [f"{col}_new" for col in modin_df.columns]
        modin_df2.columns = new_columns
        pandas_df2.columns = new_columns

    modin_dfs = (modin_df, modin_df2)
    pandas_dfs = (pandas_df, pandas_df2)

    eval_general(modin_dfs, pandas_dfs, test, iloc=[0, 1, 2])
    eval_general(modin_dfs, pandas_dfs, test, iloc=[0, -1])
    eval_general(
        modin_dfs, pandas_dfs, test, iloc=slice(1, None)
    )  # (start=1, stop=None)
    eval_general(
        modin_dfs, pandas_dfs, test, iloc=slice(None, -2)
    )  # (start=None, stop=-2)
    eval_general(
        modin_dfs,
        pandas_dfs,
        test,
        iloc=[0, 1, 5, 6, 9, 10, -2, -1],
    )
    eval_general(
        modin_dfs,
        pandas_dfs,
        test,
        iloc=[5, 4, 0, 10, 1, -1],
    )
    eval_general(
        modin_dfs, pandas_dfs, test, iloc=slice(None, None, 2)
    )  # (start=None, stop=None, step=2)


def test___setitem__single_item_in_series():
    # Test assigning a single item in a Series for issue
    # https://github.com/modin-project/modin/issues/3860
    modin_series = pd.Series(99)
    pandas_series = pandas.Series(99)
    modin_series[:1] = pd.Series(100)
    pandas_series[:1] = pandas.Series(100)
    df_equals(modin_series, pandas_series)


def test___setitem__assigning_single_categorical_sets_correct_dtypes():
    # This test case comes from
    # https://github.com/modin-project/modin/issues/3895
    modin_df = pd.DataFrame({"categories": ["A"]})
    modin_df["categories"] = pd.Categorical(["A"])
    pandas_df = pandas.DataFrame({"categories": ["A"]})
    pandas_df["categories"] = pandas.Categorical(["A"])
    df_equals(modin_df, pandas_df)


def test_iloc_assigning_scalar_none_to_string_frame():
    # This test case comes from
    # https://github.com/modin-project/modin/issues/3981
    data = [["A"]]
    modin_df = pd.DataFrame(data, dtype="string")
    modin_df.iloc[0, 0] = None
    pandas_df = pandas.DataFrame(data, dtype="string")
    pandas_df.iloc[0, 0] = None
    df_equals(modin_df, pandas_df)


@pytest.mark.parametrize(
    "value",
    [
        1,
        np.int32(1),
        1.0,
        "str val",
        pandas.Timestamp("1/4/2018"),
        np.datetime64(0, "ms"),
        True,
    ],
)
def test_loc_boolean_assignment_scalar_dtypes(value):
    modin_df, pandas_df = create_test_dfs(
        {
            "a": [1, 2, 3],
            "b": [3.0, 5.0, 6.0],
            "c": ["a", "b", "c"],
            "d": [1.0, "c", 2.0],
            "e": pandas.to_datetime(["1/1/2018", "1/2/2018", "1/3/2018"]),
            "f": [True, False, True],
        }
    )
    modin_idx, pandas_idx = pd.Series([False, True, True]), pandas.Series(
        [False, True, True]
    )

    modin_df.loc[modin_idx] = value
    pandas_df.loc[pandas_idx] = value
    df_equals(modin_df, pandas_df)


@pytest.mark.parametrize("data", test_data_values, ids=test_data_keys)
def test___len__(data):
    modin_df = pd.DataFrame(data)
    pandas_df = pandas.DataFrame(data)

    assert len(modin_df) == len(pandas_df)


def test_index_order():
    # see #1708 and #1869 for details
    df_modin, df_pandas = (
        pd.DataFrame(test_data["float_nan_data"]),
        pandas.DataFrame(test_data["float_nan_data"]),
    )
    rows_number = len(df_modin.index)
    level_0 = np.random.choice([x for x in range(10)], rows_number)
    level_1 = np.random.choice([x for x in range(10)], rows_number)
    index = pandas.MultiIndex.from_arrays([level_0, level_1])

    df_modin.index = index
    df_pandas.index = index

    for func in ["all", "any", "count"]:
        df_equals(
            getattr(df_modin, func)().index,
            getattr(df_pandas, func)().index,
        )


@pytest.mark.parametrize("data", test_data_values, ids=test_data_keys)
@pytest.mark.parametrize("sortorder", [0, 3, 5])
def test_multiindex_from_frame(data, sortorder):
    modin_df, pandas_df = create_test_dfs(data)

    def call_from_frame(df):
        if type(df).__module__.startswith("pandas"):
            return pandas.MultiIndex.from_frame(df, sortorder)
        else:
            return pd.MultiIndex.from_frame(df, sortorder)

    eval_general(modin_df, pandas_df, call_from_frame, comparator=assert_index_equal)


def test__getitem_bool_single_row_dataframe():
    # This test case comes from
    # https://github.com/modin-project/modin/issues/4845
    eval_general(pd, pandas, lambda lib: lib.DataFrame([1])[lib.Series([True])])


def test__getitem_bool_with_empty_partition():
    # This test case comes from
    # https://github.com/modin-project/modin/issues/5188

    size = MinRowPartitionSize.get()

    pandas_series = pandas.Series([True if i % 2 else False for i in range(size)])
    modin_series = pd.Series(pandas_series)

    pandas_df = pandas.DataFrame([i for i in range(size + 1)])
    pandas_df.iloc[size] = np.nan
    modin_df = pd.DataFrame(pandas_df)

    pandas_tmp_result = pandas_df.dropna()
    modin_tmp_result = modin_df.dropna()

    eval_general(
        modin_tmp_result,
        pandas_tmp_result,
        lambda df: (
            df[modin_series] if isinstance(df, pd.DataFrame) else df[pandas_series]
        ),
    )


# This is a very subtle bug that comes from:
# https://github.com/modin-project/modin/issues/4945
def test_lazy_eval_index():
    modin_df, pandas_df = create_test_dfs({"col0": [0, 1]})

    def func(df):
        df_copy = df[df["col0"] < 6].copy()
        # The problem here is that the index is not copied over so it needs
        # to get recomputed at some point. Our implementation of __setitem__
        # requires us to build a mask and insert the value from the right
        # handside into the new DataFrame. However, it's possible that we
        # won't have any new partitions, so we will end up computing an empty
        # index.
        df_copy["col0"] = df_copy["col0"].apply(lambda x: x + 1)
        return df_copy

    eval_general(modin_df, pandas_df, func)


def test_index_of_empty_frame():
    # Test on an empty frame created by user
    md_df, pd_df = create_test_dfs(
        {}, index=pandas.Index([], name="index name"), columns=["a", "b"]
    )
    assert md_df.empty and pd_df.empty
    df_equals(md_df.index, pd_df.index)

    # Test on an empty frame produced by Modin's logic
    data = test_data_values[0]
    md_df, pd_df = create_test_dfs(
        data, index=pandas.RangeIndex(len(next(iter(data.values()))), name="index name")
    )

    md_res = md_df.query(f"{md_df.columns[0]} > {RAND_HIGH}")
    pd_res = pd_df.query(f"{pd_df.columns[0]} > {RAND_HIGH}")

    assert md_res.empty and pd_res.empty
    df_equals(md_res.index, pd_res.index)
