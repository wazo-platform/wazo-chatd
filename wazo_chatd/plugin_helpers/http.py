# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later


def update_model_instance(model_instance, model_instance_data):
    for attribute_name, attribute_value in model_instance_data.items():
        if not hasattr(model_instance, attribute_name):
            raise TypeError(
                f'{model_instance.__class__.__name__} has no attribute {attribute_name}'
            )
        setattr(model_instance, attribute_name, attribute_value)
