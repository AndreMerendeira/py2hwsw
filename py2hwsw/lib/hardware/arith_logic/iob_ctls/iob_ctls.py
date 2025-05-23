# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT


def setup(py_params_dict):
    attributes_dict = {
        "generate_hw": False,
        "subblocks": [
            {
                "core_name": "iob_reverse",
                "instance_name": "iob_reverse_inst",
            },
            {
                "core_name": "iob_prio_enc",
                "instance_name": "iob_prio_enc_inst",
            },
        ],
    }

    return attributes_dict
