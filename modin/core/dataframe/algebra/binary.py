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

"""Module houses builder class for Binary operator."""

import numpy as np
import pandas

from .operator import Operator


def int_to_float64(dtype: np.dtype) -> np.dtype:
    """
    Check if a datatype is a variant of integer.

    If dtype is integer function returns float64 datatype if not returns the
    argument datatype itself

    Parameters
    ----------
    dtype : np.dtype
        NumPy datatype.

    Returns
    -------
    dtype : np.dtype
        Returns float64 for all int datatypes or returns the datatype itself
        for other types.

    Notes
    -----
    Used to precompute datatype in case of division in pandas
    """
    if dtype in np.sctypes["int"] + np.sctypes["uint"]:
        return np.dtype(np.float64)
    else:
        return dtype


# To precompute datatypes for binary operations which follow pandas find_common_type
def compute_dtypes_common_cast(first, second) -> np.dtype:
    """
    Precompute data types for those binary operations by finding common type between operands.

    Parameters
    ----------
    first : PandasQueryCompiler
        Operand dataframe for which the binary operation would be performed later.
    second : PandasQueryCompiler
        Operand dataframe for which the binary operation would be performed later.

    Returns
    -------
    dtypes
        The pandas series with precomputed dtypes.
    """
    dtypes_first = dict(zip(first.columns, first.dtypes))
    dtypes_second = dict(zip(second.columns, second.dtypes))
    columns_first = set(first.columns)
    columns_second = set(second.columns)
    common_columns = columns_first.intersection(columns_second)
    mismatch_columns = columns_first.union(columns_second) - common_columns
    # If one columns dont match the result of the non matching column would be nan.
    nan_dtype = np.dtype(type(np.nan))
    dtypes = pandas.Series(
        [
            pandas.core.dtypes.cast.find_common_type(
                [
                    dtypes_first[x],
                    dtypes_second[x],
                ]
            )
            for x in common_columns
        ],
        index=common_columns,
    )
    dtypes = pandas.concat(
        [
            dtypes,
            pandas.Series(
                [nan_dtype] * (len(mismatch_columns)),
                index=mismatch_columns,
            ),
        ]
    )
    dtypes = dtypes.sort_index()
    return dtypes


class Binary(Operator):
    """Builder class for Binary operator."""

    @classmethod
    def register(
        cls,
        func,
        join_type="outer",
        labels="replace",
        how_compute_dtypes=None,
    ):
        """
        Build template binary operator.

        Parameters
        ----------
        func : callable(pandas.DataFrame, [pandas.DataFrame, list-like, scalar]) -> pandas.DataFrame
            Binary function to execute. Have to be able to accept at least two arguments.
        join_type : {'left', 'right', 'outer', 'inner', None}, default: 'outer'
            Type of join that will be used if indices of operands are not aligned.
        labels : {"keep", "replace", "drop"}, default: "replace"
            Whether keep labels from left Modin DataFrame, replace them with labels
            from joined DataFrame or drop altogether to make them be computed lazily later.
        how_compute_dtypes : {"common_cast", "float","bool", None}, default: None
            How dtypes should be computed.
            If "common_cast" casts to common dtype of operand columns.
            If "float" performs type casting by finding common dtype, if the common dtype is any of the
            integer types perform type casting to float. Used in case of truediv.
            If "bool" dtypes would be a boolean series with same size as that of operands.
            If ``None`` do not infer new dtypes (they will be computed manually once accessed).

        Returns
        -------
        callable
            Function that takes query compiler and executes binary operation.
        """

        def caller(
            query_compiler, other, broadcast=False, *args, dtypes=None, **kwargs
        ):
            """
            Apply binary `func` to passed operands.

            Parameters
            ----------
            query_compiler : QueryCompiler
                Left operand of `func`.
            other : QueryCompiler, list-like object or scalar
                Right operand of `func`.
            broadcast : bool, default: False
                If `other` is a one-column query compiler, indicates whether it is a Series or not.
                Frames and Series have to be processed differently, however we can't distinguish them
                at the query compiler level, so this parameter is a hint that passed from a high level API.
            *args : args,
                Arguments that will be passed to `func`.
            dtypes : "copy" or None, default: None
                Whether to keep old dtypes or infer new dtypes from data.
            **kwargs : kwargs,
                Arguments that will be passed to `func`.

            Returns
            -------
            QueryCompiler
                Result of binary function.
            """
            axis = kwargs.get("axis", 0)
            if isinstance(other, type(query_compiler)):
                if broadcast:
                    assert (
                        len(other.columns) == 1
                    ), "Invalid broadcast argument for `broadcast_apply`, too many columns: {}".format(
                        len(other.columns)
                    )
                    # Transpose on `axis=1` because we always represent an individual
                    # column or row as a single-column Modin DataFrame
                    if axis == 1:
                        other = other.transpose()
                    return query_compiler.__constructor__(
                        query_compiler._modin_frame.broadcast_apply(
                            axis,
                            lambda left, right: func(
                                left, right.squeeze(), *args, **kwargs
                            ),
                            other._modin_frame,
                            join_type=join_type,
                            labels=labels,
                            dtypes=dtypes,
                        )
                    )
                else:
                    if (
                        other._modin_frame._dtypes is not None
                        and query_compiler._modin_frame._dtypes is not None
                        and other.is_series_like is False
                    ):
                        if how_compute_dtypes == "bool":
                            dtypes = pandas.Series([bool] * len(other.dtypes))
                        if how_compute_dtypes == "common_cast":
                            dtypes = compute_dtypes_common_cast(query_compiler, other)
                        elif how_compute_dtypes == "float":
                            dtypes = compute_dtypes_common_cast(query_compiler, other)
                            dtypes = dtypes.apply(int_to_float64)
                    return query_compiler.__constructor__(
                        query_compiler._modin_frame.n_ary_op(
                            lambda x, y: func(x, y, *args, **kwargs),
                            [other._modin_frame],
                            join_type=join_type,
                            dtypes=dtypes,
                        )
                    )

            else:
                # TODO: it's possible to chunk the `other` and broadcast them to partitions
                # accordingly, in that way we will be able to use more efficient `._modin_frame.map()`
                if isinstance(other, (dict, list, np.ndarray, pandas.Series)):
                    new_modin_frame = query_compiler._modin_frame.apply_full_axis(
                        axis,
                        lambda df: func(df, other, *args, **kwargs),
                        new_index=query_compiler.index,
                        new_columns=query_compiler.columns,
                        dtypes=dtypes,
                    )
                else:
                    new_modin_frame = query_compiler._modin_frame.map(
                        lambda df: func(df, other, *args, **kwargs),
                        dtypes=dtypes,
                    )
                return query_compiler.__constructor__(new_modin_frame)

        return caller
