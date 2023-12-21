import numpy as np
import pandas as pd
import warnings
import os
import scqubits as scq
from scqubits.core.transmon import TunableTransmon
from pandasai import SmartDataframe
from pandasai.llm import OpenAI, Starcoder, Falcon
from dotenv import load_dotenv

from squadds.core.metrics import *
from squadds.core.db import SQuADDS_DB


"""
=====================================================================================
HELPER FUNCTIONS
=====================================================================================
"""
# Helper function to scale values with 'um' in them
def scale_value(value, ratio):
    # Remove 'um' from the value, convert to float, scale and convert back to string
    scaled_value = str(float(value.replace('um', '')) * ratio) + 'um'
    return scaled_value

"""
=====================================================================================
Analyzer
=====================================================================================
"""
class Analyzer:

    __supported_metrics__ = ['Euclidean', 'Manhattan', 'Chebyshev', 'Weighted Euclidean' , 'Custom']
    __supported_estimation_methods__ = ['Interpolation']

    def __init__(self, db):
        """
        Args:
            db (SQuADDS_DB): The database to analyze.

        Attributes:
            db (SQuADDS_DB): The database to analyze.
            metric_strategy (MetricStrategy): The strategy to use for calculating the distance metric.
            custom_metric_func (function): The custom function to use for calculating the distance metric.
            metric_weights (dict): The weights to use for calculating the weighted distance metric.

        Raises:
            ValueError: If the specified metric is not supported.
        """

        self.db = db

        self.selected_component_name = self.db.selected_component_name
        self.selected_component = self.db.selected_component
        self.selected_data_type = self.db.selected_data_type
        self.selected_confg = self.db.selected_confg
        self.selected_qubit = self.db.selected_qubit
        self.selected_cavity = self.db.selected_cavity
        self.selected_coupler = self.db.selected_coupler
        self.selected_system = self.db.selected_system
        self.df = self.db.selected_df
        self.closest_designs = None
        self.closest_df_entry = None
        self.interpolate_design = None

        self.H_param_keys = self.db.target_param_keys
        self.metric_strategy = None  # Will be set dynamically
        self.custom_metric_func = None
        self.metric_weights = None
        self.smart_df = None
        self.coupling_type = None

    def target_param_keys(self):
        """
        Returns:
            list: The target parameter keys.
        """
        return self.db.target_param_keys

    def set_metric_strategy(self, strategy: MetricStrategy):
        """
        Sets the metric strategy to use for calculating the distance metric.

        Args:
            strategy (MetricStrategy): The strategy to use for calculating the distance metric.

        Raises:
            ValueError: If the specified metric is not supported.
        """

        self.metric_strategy = strategy

    def _outside_bounds(self, df: pd.DataFrame, params: dict, display=True) -> bool:
        """
        Check if entered parameters are outside the bounds of a dataframe.

        Args:
            df (pd.DataFrame): Dataframe to give warning.
            params (dict): Keys are column names of `df`. Values are values to check for bounds.
        
        Returns:
            bool: True if any value is outside of bounds. False if all values are inside bounds.
        """
        outside_bounds = False
        filtered_df = df.copy()

        for param, value in params.items():
            if param not in df.columns:
                raise ValueError(f"{param} is not a column in dataframe: {df}")

            if isinstance(value, (int, float)):
                if value < df[param].min() or value > df[param].max():
                    if display:
                        logging.info(f"\033[1mNOTE TO USER:\033[0m the value \033[1m{value} for {param}\033[0m is outside the bounds of our library.\nIf you find a geometry which corresponds to these values, please consider contributing it! 😁🙏\n")
                    outside_bounds = True

            elif isinstance(value, str):
                filtered_df = filtered_df[filtered_df[param] == value]

            else:
                raise ValueError(f"Unsupported type {type(value)} for parameter {param}")

        if filtered_df.empty:
            categorical_params = {key: value for key, value in params.items() if isinstance(value, str)}
            if display and categorical_params:
                logging.info(f"\033[1mNOTE TO USER:\033[0m There are no geometries with the specified categorical parameters - \033[1m{categorical_params}\033[0m.\nIf you find a geometry which corresponds to these values, please consider contributing it! 😁🙏\n")
            outside_bounds = True

        return outside_bounds


    def find_closest(self,
                     target_params: dict,
                     num_top: int,
                     metric: str = 'Euclidean',
                     display: bool = True):
        """
        """
        ### Checks
        # Check for supported metric
        if metric not in self.__supported_metrics__:
            raise ValueError(f'`metric` must be one of the following: {self.__supported_metrics__}')
        # Check for improper size of library
        if (num_top > len(self.df)):
            raise ValueError('`num_top` cannot be bigger than size of read-in library.')

        # Log if parameters outside of library
        filtered_df = self.df[self.H_param_keys]  # Filter DataFrame based on H_param_keys
        self._outside_bounds(df=filtered_df, params=target_params, display=display)

        # Set strategy dynamically based on the metric parameter
        if metric == 'Euclidean':
            self.set_metric_strategy(EuclideanMetric())
        elif metric == 'Manhattan':
            self.set_metric_strategy(ManhattanMetric())
        elif metric == 'Chebyshev':
            self.set_metric_strategy(ChebyshevMetric())
        elif metric == 'Weighted Euclidean':
            self.set_metric_strategy(WeightedEuclideanMetric(self.metric_weights))
        elif metric == 'Custom':
            self.set_metric_strategy(CustomMetric(self.custom_metric_func))

        if not self.metric_strategy:
            raise ValueError("Invalid metric.")

        # Main logic
        distances = filtered_df.apply(lambda row: self.metric_strategy.calculate(target_params, row), axis=1)

        # Sort distances and get the closest ones
        sorted_indices = distances.nsmallest(num_top).index
        closest_df = self.df.loc[sorted_indices]

        return closest_df

    def get_interpolated_design(self,
                     target_params: dict,
                     metric: str = 'Euclidean',
                     display: bool = True):
        """
        """
        raise NotImplementedError
    

    def get_design(self, df):
        """
        Extracts the design parameters from the dataframe and returns a dict.
        """
        return df["design_options"].to_dict()[0]

    def get_param(self, design, param):
        """
        Extracts a specific parameter from the design dict.
        """
        raise NotImplementedError

    def interpolate_design(self, updated_design1, updated_design2):
        """
        Interpolates the design parameters of the resonator and qubit to the design dict.
        """
        raise NotImplementedError
