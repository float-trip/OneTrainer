import json
import os.path
from pathlib import Path

from safetensors.torch import save_file
import torch
from torch import Tensor

from modules.model.BaseModel import BaseModel
from modules.model.KandinskyModel import KandinskyModel
from modules.modelSaver.BaseModelSaver import BaseModelSaver
from modules.util.enum.ModelFormat import ModelFormat
from modules.util.enum.ModelType import ModelType


class KandinskyLoRAModelSaver(BaseModelSaver):

    @staticmethod
    def __get_state_dict(model: KandinskyModel) -> dict[str, Tensor]:
        state_dict = {}
        if model.unet_lora is not None:
            state_dict |= model.unet_lora.state_dict()

        return state_dict

    @staticmethod
    def __save_ckpt(
            model: KandinskyModel,
            destination: str,
            dtype: torch.dtype,
    ):

        state_dict = KandinskyLoRAModelSaver.__get_state_dict(model)
        save_state_dict = BaseModelSaver._convert_state_dict_dtype(state_dict, dtype)

        os.makedirs(Path(destination).parent.absolute(), exist_ok=True)
        torch.save(save_state_dict, destination)

    @staticmethod
    def __save_safetensors(
            model: KandinskyModel,
            destination: str,
            dtype: torch.dtype,
    ):

        state_dict = KandinskyLoRAModelSaver.__get_state_dict(model)
        save_state_dict = BaseModelSaver._convert_state_dict_dtype(state_dict, dtype)

        os.makedirs(Path(destination).parent.absolute(), exist_ok=True)
        save_file(save_state_dict, destination)

    @staticmethod
    def __save_internal(
            model: KandinskyModel,
            destination: str,
    ):
        os.makedirs(destination, exist_ok=True)

        # lora
        KandinskyLoRAModelSaver.__save_ckpt(
            model,
            os.path.join(destination, "lora", "lora.pt"),
            torch.float32
        )

        # optimizer
        os.makedirs(os.path.join(destination, "optimizer"), exist_ok=True)
        torch.save(model.optimizer.state_dict(), os.path.join(destination, "optimizer", "optimizer.pt"))

        # ema
        if model.ema:
            os.makedirs(os.path.join(destination, "ema"), exist_ok=True)
            torch.save(model.ema.state_dict(), os.path.join(destination, "ema", "ema.pt"))

        # meta
        with open(os.path.join(destination, "meta.json"), "w") as meta_file:
            json.dump({
                'train_progress': {
                    'epoch': model.train_progress.epoch,
                    'epoch_step': model.train_progress.epoch_step,
                    'epoch_sample': model.train_progress.epoch_sample,
                    'global_step': model.train_progress.global_step,
                },
            }, meta_file)

    def save(
            self,
            model: BaseModel,
            model_type: ModelType,
            output_model_format: ModelFormat,
            output_model_destination: str,
            dtype: torch.dtype,
    ):
        match output_model_format:
            case ModelFormat.DIFFUSERS:
                raise NotImplementedError
            case ModelFormat.CKPT:
                self.__save_ckpt(model, output_model_destination, dtype)
            case ModelFormat.SAFETENSORS:
                self.__save_safetensors(model, output_model_destination, dtype)
            case ModelFormat.INTERNAL:
                self.__save_internal(model, output_model_destination)
